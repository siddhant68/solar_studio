"""D02/D03 benchmarks with measured peak process-tree memory.

    python scripts/benchmark.py OUT.json

Each case runs in a fresh child process; the parent samples the resident set size of
the child and all its descendants every 10 ms (psutil) and reports the peak sum. Exports
run in a separate child so they are measured separately from generation.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def machine() -> dict:
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "cpu_model": cpu,
        "logical_cpus": psutil.cpu_count(logical=True),
        "memory_total_mib": round(psutil.virtual_memory().total / 2**20),
        "os": platform.platform(),
        "python": platform.python_version(),
        "runner": "Claude Code cloud container (Linux x86_64)",
    }


def run_measured(args: list[str], env: dict | None = None) -> dict:
    e = dict(os.environ)
    if env:
        e.update(env)
    t0 = time.perf_counter()
    proc = subprocess.Popen([PY, *args], cwd=str(ROOT), env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ps = psutil.Process(proc.pid)
    peak = 0
    samples = 0
    while proc.poll() is None:
        try:
            procs = [ps] + ps.children(recursive=True)
            rss = 0
            for p in procs:
                try:
                    rss += p.memory_info().rss
                except psutil.NoSuchProcess:
                    pass
            peak = max(peak, rss)
            samples += 1
        except psutil.NoSuchProcess:
            pass
        time.sleep(0.01)
    out, err = proc.communicate()
    return {"exit": proc.returncode, "wall_s": time.perf_counter() - t0, "peak_tree_rss_mib": round(peak / 2**20, 2), "rss_samples": samples, "stderr_tail": err.decode()[-400:]}


def case(name: str, fixture: Path, data_dir: Path, tmp: Path, env: dict | None = None, exports: bool = True) -> dict:
    out = tmp / f"{name}-generate.json"
    m = run_measured([str(ROOT / "scripts" / "bench_case.py"), "generate", str(fixture), str(data_dir), str(out)], env)
    res = json.loads(out.read_text()) if out.exists() else {"ok": False, "error": "no output"}
    rec = {"case": name, "fixture": str(fixture.relative_to(ROOT)), "generate": {**m, **res}}
    if exports and res.get("ok"):
        out2 = tmp / f"{name}-export.json"
        m2 = run_measured([str(ROOT / "scripts" / "bench_case.py"), "export", res["result_id"], str(data_dir), str(out2)])
        rec["exports"] = {**m2, **json.loads(out2.read_text())}
    return rec


def main(out_path: str) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="solar-bench-"))
    try:
        results = []
        d02 = case("D02-10k", ROOT / "fixtures" / "benchmark-10k.request.json", tmp / "d02", tmp)
        g = d02["generate"]
        d02["gate"] = {
            "requirement": ">= 10,000 modules generated and verified in <= 20 s with peak process-tree memory <= 512 MiB",
            "module_count": g.get("module_count"),
            "generate_and_verify_s": g.get("timings", {}).get("generate_and_verify_total_s"),
            "process_wall_s_including_interpreter_start": g["wall_s"],
            "peak_tree_rss_mib": g["peak_tree_rss_mib"],
            "pass": bool(g.get("ok") and g.get("module_count", 0) >= 10_000 and g["wall_s"] <= 20 and g["peak_tree_rss_mib"] <= 512),
        }
        results.append(d02)
        d03 = case("D03-25k", ROOT / "fixtures" / "stress-25k.request.json", tmp / "d03", tmp)
        d03["gate"] = {"requirement": "25,000-module stress fixture completes or is rejected by a declared limit before committing partial output", "completed": bool(d03["generate"].get("ok")), "module_count": d03["generate"].get("module_count")}
        results.append(d03)
        # D03 limit demonstrations
        t_out = case("D03-timeout-0.05s", ROOT / "fixtures" / "stress-25k.request.json", tmp / "d03-timeout", tmp, env={"SOLAR_LAYOUT_TIMEOUT_S": "0.05"}, exports=False)
        t_out["gate"] = {"requirement": "finite timeout returns a typed RESOURCE_LIMIT and stores nothing", "pass": t_out["generate"].get("ok") is False and t_out["generate"].get("error", {}).get("code") == "RESOURCE_LIMIT" and t_out["generate"].get("stored_results") == 0}
        results.append(t_out)
        big = json.loads((ROOT / "fixtures" / "stress-25k.request.json").read_text())
        big["placement"]["row_pitch_m"] = 4.5
        big["placement"]["minimum_clear_row_gap_m"] = 0.3
        big["boundary"]["coordinates"] = [[[500000.0 + x, 4200000.0 + y] for x, y in ring] for ring in [[[0, 0], [1400, 0], [1400, 900], [0, 900], [0, 0]]]]
        big["exclusions"] = []
        (tmp / "over-output-limit.json").write_text(json.dumps(big))
        # derived fixture lives in the temp folder, so run it directly
        out = tmp / "D03-output-limit-generate.json"
        m = run_measured([str(ROOT / "scripts" / "bench_case.py"), "generate", str(tmp / "over-output-limit.json"), str(tmp / "d03-out"), str(out)])
        o = {"case": "D03-output-limit", "fixture": "derived: 1400 x 900 m site, 2x14 tables, pitch 4.5 m", "generate": {**m, **json.loads(out.read_text())}}
        o["gate"] = {"requirement": "output above the declared module limit is rejected before anything is committed", "pass": o["generate"].get("ok") is False and o["generate"].get("error", {}).get("details", {}).get("limit") == "max_modules" and o["generate"].get("stored_results") == 0}
        results.append(o)
        tiny = json.loads((ROOT / "fixtures" / "stress-25k.request.json").read_text())
        tiny["boundary"]["coordinates"] = [[[500000.0 + x, 4200000.0 + y] for x, y in [[0, 0], [14000, 0], [14000, 14000], [0, 14000], [0, 0]]]]
        tiny["exclusions"] = []
        tiny["module"].update(width_m=0.05, length_m=0.05)
        tiny["table"].update(rows=1, columns=1, tilt_deg=0.0)
        tiny["placement"].update(table_gap_m=0.0, row_pitch_m=0.05, minimum_clear_row_gap_m=0.0)
        (tmp / "over-candidate-limit.json").write_text(json.dumps(tiny))
        out = tmp / "D03-candidate-limit-generate.json"
        m = run_measured([str(ROOT / "scripts" / "bench_case.py"), "generate", str(tmp / "over-candidate-limit.json"), str(tmp / "d03-cand"), str(out)])
        c = {"case": "D03-candidate-limit", "fixture": "derived: 14 x 14 km site, 0.05 m tables", "generate": {**m, **json.loads(out.read_text())}}
        c["gate"] = {"requirement": "candidate bound is enforced before unbounded work", "pass": c["generate"].get("ok") is False and c["generate"].get("error", {}).get("details", {}).get("limit") in ("max_candidates_total", "max_candidates_per_phase") and c["generate"]["elapsed_s"] < 2.0}
        results.append(c)
        from solar_layout import policy

        report = {
            "schema": "solar.benchmarks/1",
            "machine": machine(),
            "declared_limits": policy.LIMITS,
            "method": "fresh child process per case; process-tree RSS sampled every 10 ms with psutil (peak of the sum over the child and its descendants); exports in a separate child",
            "cases": results,
        }
        Path(out_path).write_text(json.dumps(report, indent=1))
        for r in results:
            print(r["case"], json.dumps(r.get("gate")))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
