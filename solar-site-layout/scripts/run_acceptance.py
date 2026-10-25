"""Run the acceptance evidence for the current source commit and write reports/ACCEPTANCE.json.

    .venv/bin/python scripts/run_acceptance.py [--skip-bench] [--inspector-dir DIR]

Steps (all against the checked-out commit; refuses to run on uncommitted source changes):
 1. pytest (all tests, including the real-browser V01-V03 and real-MCP S02 runs) with
    JUnit XML; evidence written under evidence/acceptance/.
 2. CLI calculation examples for every analytic fixture (generate + all exports) and the
    3-4-5 pitch example, into evidence/examples/.
 3. Benchmarks (D02/D03) into reports/BENCHMARKS.json.
 4. Optional MCP Inspector cross-check (second MCP client implementation).
 The gate table is built afterwards by scripts/build_acceptance_report.py from these
 outputs, the reference evidence and the packaging/reproduction logs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
PY = sys.executable
FIX = REPO / "handoffs" / "module-01" / "fixtures"
EVID = ROOT / "evidence"
ACC = EVID / "acceptance"

SOURCE_PATHS = ["solar-site-layout/src", "solar-site-layout/tests", "solar-site-layout/scripts", "solar-site-layout/pyproject.toml", "solar-site-layout/uv.lock", "solar-site-layout/fixtures", "solar-site-layout/references/probes"]

def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def git(*args: str) -> str:
    return sh(["git", "-C", str(REPO), *args]).stdout.strip()


def source_tree_ids(commit: str) -> dict[str, str]:
    return {p: git("rev-parse", f"{commit}:{p}") for p in SOURCE_PATHS}


def run_pytest() -> dict:
    ACC.mkdir(parents=True, exist_ok=True)
    junit = ACC / "pytest-junit.xml"
    env = dict(os.environ, SOLAR_EVIDENCE_DIR=str(ACC))
    t0 = time.time()
    p = sh([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"], cwd=str(ROOT), env=env, timeout=3600)
    (ACC / "pytest-output.txt").write_text(p.stdout + "\n" + p.stderr)
    cases = []
    for tc in ET.parse(junit).getroot().iter("testcase"):
        outcome = "passed"
        for child in tc:
            if child.tag in ("failure", "error"):
                outcome = "failed"
            elif child.tag == "skipped":
                outcome = "skipped"
        cases.append({"file": tc.get("classname", "").split(".")[-1] + ".py", "name": tc.get("name"), "outcome": outcome, "seconds": float(tc.get("time", 0))})
    return {"exit": p.returncode, "seconds": round(time.time() - t0, 1), "cases": cases, "command": f"SOLAR_EVIDENCE_DIR=evidence/acceptance {Path(PY).name} -m pytest -q --junitxml=evidence/acceptance/pytest-junit.xml"}


def cli_examples() -> dict:
    out = EVID / "examples"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    data = out / "_data"
    log = []
    results = {}

    def cli(*args):
        p = sh([PY, "-m", "solar_layout.cli", "--data-dir", str(data), *args], cwd=str(ROOT))
        log.append({"command": "solar-layout --data-dir evidence/examples/_data " + " ".join(str(a).replace(str(REPO) + "/", "") for a in args), "exit": p.returncode})
        return p.returncode, json.loads(p.stdout)

    for name in ("rectangle", "obstacle", "multipolygon", "concave-notch", "hole"):
        rc, res = cli("generate", str(FIX / f"{name}.request.json"))
        r = res["result"]
        d = out / name
        d.mkdir()
        files = {}
        for fmt in ("json", "csv", "svg", "dxf", "report"):
            rc2, ex = cli("export", r["result_id"], "--format", fmt)
            src = Path(ex["result"]["absolute_path"])
            shutil.copy(src, d / src.name.split("-", 1)[1])
            files[fmt] = {"file": f"{name}/{src.name.split('-', 1)[1]}", "sha256": ex["result"]["sha256"]}
        (d / "summary.json").write_text(json.dumps({k: r[k] for k in ("result_id", "input_digest", "payload_digest")} | {"quantities": r["summary"]["quantities"], "dimensions": r["summary"]["dimensions"], "placement": r["summary"]["placement"], "warnings": r["summary"]["warnings"], "verification": r["verification"]}, indent=1))
        results[name] = {"result_id": r["result_id"], "modules": r["summary"]["quantities"]["module_count"], "tables": r["summary"]["quantities"]["table_count"], "dc_kwp": r["summary"]["quantities"]["dc_capacity_kwp"], "files": files}
    rc, pitch = cli("pitch", str(FIX / "pitch-3-4-5.request.json"))
    (out / "pitch-3-4-5.result.json").write_text(json.dumps(pitch["result"], indent=1))
    results["pitch-3-4-5"] = {k: pitch["result"][k] for k in ("projected_depth_m", "table_rise_m", "shadow_clear_gap_m", "pitch_at_that_elevation_m", "recommended_pitch_m")}
    bad = json.loads((FIX / "rectangle.request.json").read_text())
    bad["frame"]["units"] = "deg"
    (data / "bad-units.json").write_text(json.dumps(bad))
    rc, err = cli("generate", str(data / "bad-units.json"))
    results["error-example"] = {"exit": rc, "error": err["error"]}
    shutil.rmtree(data)
    (out / "cli-log.json").write_text(json.dumps(log, indent=1))
    (out / "INDEX.json").write_text(json.dumps(results, indent=1))
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-bench", action="store_true")
    ap.add_argument("--inspector-dir")
    args = ap.parse_args()
    dirty = git("status", "--porcelain", "--", *SOURCE_PATHS)
    if dirty:
        print("refusing: uncommitted source changes:\n" + dirty)
        return 2
    commit = git("rev-parse", "HEAD")
    started = datetime.now(timezone.utc).isoformat()
    print("source commit", commit)
    pt = run_pytest()
    print("pytest exit", pt["exit"], "cases", len(pt["cases"]))
    ex = cli_examples()
    print("examples", {k: v.get("modules") for k, v in ex.items() if isinstance(v, dict)})
    bench = None
    if not args.skip_bench:
        p = sh([PY, str(ROOT / "scripts" / "benchmark.py"), str(ROOT / "reports" / "BENCHMARKS.json")], cwd=str(ROOT), timeout=1800)
        (ACC / "benchmark-output.txt").write_text(p.stdout + p.stderr)
        bench = json.loads((ROOT / "reports" / "BENCHMARKS.json").read_text())
    insp = None
    if args.inspector_dir:
        out = ACC / "mcp-inspector"
        if out.exists():
            shutil.rmtree(out)
        p = sh(["bash", str(ROOT / "scripts" / "mcp_inspector_crosscheck.sh"), args.inspector_dir, str(out)], cwd=str(ROOT), timeout=900)
        (out / "run.txt").write_text(p.stdout + p.stderr)
        try:
            calls = {n: json.loads((out / f"{n}.json").read_text()) for n in ("tools-list", "call-pitch", "call-generate", "call-bad-items")}
            sc = lambda d: d.get("structuredContent") or json.loads(d["content"][0]["text"])  # noqa: E731
            insp = {
                "tools": [t["name"] for t in calls["tools-list"]["tools"]],
                "pitch_recommended_m": sc(calls["call-pitch"])["recommended_pitch_m"],
                "rectangle_result_id": sc(calls["call-generate"])["result_id"],
                "rectangle_modules": sc(calls["call-generate"])["summary"]["quantities"]["module_count"],
                "bad_items_error": sc(calls["call-bad-items"])["error"]["code"],
            }
        except (OSError, ValueError, KeyError) as e:
            insp = {"error": str(e)}
        if (out / "data").exists():
            shutil.rmtree(out / "data")
        catalog = out / "catalog.json"
        if catalog.exists():
            catalog.unlink()
    (ACC / "run-meta.json").write_text(json.dumps({"source_commit": commit, "source_tree_ids": source_tree_ids(commit), "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(), "pytest": {k: pt[k] for k in ("exit", "seconds", "command")}, "test_count": len(pt["cases"]), "inspector": insp}, indent=1))
    (ACC / "pytest-cases.json").write_text(json.dumps(pt["cases"], indent=1))
    print("done; build the gate table with scripts/build_acceptance_report.py")
    return 0 if pt["exit"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
