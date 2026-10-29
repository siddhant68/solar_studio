"""TD02 terrain benchmark (handoffs/module-02-terrain/PLAN.md section 11).

    python scripts/terrain_benchmark.py OUT.json

Construction:
* layout: Module 01 fixtures/benchmark-10k.request.json (10,192 modules, 364 tables);
* terrain: a regular 501 x 501-vertex grid (500,000 triangles, each cell split on a fixed
  diagonal) over the site boundary's bounding box plus a 10 m margin, in the layout's
  frame, with a local vertical reference; z = 100 + 0.02 x' + 0.03 y' +
  0.4 sin(x'/9) cos(y'/13), x', y' local to the grid origin;
* supports: 6 explicit points per table, (0|W/2|W, 0|D); clearance 0.5 m, structure depth
  0.1 m, limits 30 deg and 10 m so that every table is placed.

Phases, each in a fresh child process (scripts/terrain_bench_case.py), with wall time and
peak process-tree RSS sampled every 10 ms by this parent (psutil):
1. terrain import: surface JSON file on disk -> validated, prepared and stored terrain;
2. placement (TD02): layout and prepared terrain already stored -> computed, independently
   verified and persisted placement. Target <= 30 s process wall time (interpreter start
   included) and <= 1 GiB peak process-tree memory. A miss is reported as a fail; the
   target is not changed to fit;
3. cold workflow: nothing stored -> layout + import + placement in one process.
Exit status 1 if TD02 fails.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
CASE = ROOT / "scripts" / "terrain_bench_case.py"
GRID_N = 501
MARGIN_M = 10.0
WALL_TARGET_S = 30.0
MEMORY_TARGET_MIB = 1024.0


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
        "physical_cpus": psutil.cpu_count(logical=False),
        "memory_total_mib": round(psutil.virtual_memory().total / 2**20),
        "os": platform.platform(),
        "python": platform.python_version(),
        "runner": os.environ.get("SOLAR_BENCH_RUNNER") or ("GitHub Actions " + os.environ.get("ImageOS", "") if os.environ.get("GITHUB_ACTIONS") else "local"),
    }


def run_measured(args: list[str]) -> dict:
    t0 = time.perf_counter()
    proc = subprocess.Popen([PY, *args], cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ps = psutil.Process(proc.pid)
    peak = samples = 0
    while proc.poll() is None:
        try:
            rss = 0
            for p in [ps] + ps.children(recursive=True):
                try:
                    rss += p.memory_info().rss
                except psutil.NoSuchProcess:
                    pass
            peak = max(peak, rss)
            samples += 1
        except psutil.NoSuchProcess:
            pass
        time.sleep(0.01)
    _, err = proc.communicate()
    return {"exit": proc.returncode, "wall_s": round(time.perf_counter() - t0, 3), "peak_tree_rss_mib": round(peak / 2**20, 1), "rss_samples": samples, "stderr_tail": err.decode()[-600:]}


def phase(name: str, args: list[str], out: Path) -> dict:
    m = run_measured([str(CASE), name, *[str(a) for a in args], str(out)])
    res = json.loads(out.read_text()) if out.exists() else {"ok": False, "error": "no output"}
    return {**m, **res}


def build_surface(layout_req: dict, frame: dict) -> tuple[dict, dict]:
    ring = np.array(layout_req["boundary"]["coordinates"][0], dtype=np.float64)
    lo, hi = ring.min(axis=0) - MARGIN_M, ring.max(axis=0) + MARGIN_M
    xs, ys = np.linspace(lo[0], hi[0], GRID_N), np.linspace(lo[1], hi[1], GRID_N)
    X, Y = np.meshgrid(xs, ys)
    xp, yp = X - lo[0], Y - lo[1]
    Z = 100.0 + 0.02 * xp + 0.03 * yp + 0.4 * np.sin(xp / 9.0) * np.cos(yp / 13.0)
    V = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    i, j = np.meshgrid(np.arange(GRID_N - 1), np.arange(GRID_N - 1))
    a = (j * GRID_N + i).ravel()
    T = np.concatenate([np.stack([a, a + 1, a + GRID_N + 1], 1), np.stack([a, a + GRID_N + 1, a + GRID_N], 1)])
    doc = {
        "schema_version": "solar.terrain.surface/1",
        "name": "TD02 benchmark grid",
        "frame": frame,
        "vertical": {"kind": "local", "id": "local:td02-benchmark", "units": "m", "positive": "up"},
        "source": {"kind": "synthetic_analytic", "description": "z = 100 + 0.02 x' + 0.03 y' + 0.4 sin(x'/9) cos(y'/13); PLAN.md section 11"},
        "vertices_xyz_m": V.tolist(),
        "triangles": T.tolist(),
    }
    construction = {
        "grid_vertices": f"{GRID_N} x {GRID_N}",
        "vertices": int(len(V)),
        "triangles": int(len(T)),
        "bbox_xy_m": [float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])],
        "cell_m": [float((hi[0] - lo[0]) / (GRID_N - 1)), float((hi[1] - lo[1]) / (GRID_N - 1))],
        "covers": "site boundary bounding box plus a 10 m margin",
        "diagonal": "each cell split as (i,j)-(i+1,j)-(i+1,j+1) and (i,j)-(i+1,j+1)-(i,j+1)",
        "z": "100 + 0.02 x' + 0.03 y' + 0.4 sin(x'/9) cos(y'/13), x' = x - bbox_min_x, y' = y - bbox_min_y",
    }
    return doc, construction


def main(out_path: str) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="terrain-bench-"))
    try:
        layout_path = ROOT / "fixtures" / "benchmark-10k.request.json"
        layout_req = json.loads(layout_path.read_text())
        data = tmp / "data"
        lay = phase("layout", [layout_path, data], tmp / "layout.json")
        assert lay["ok"], lay
        from solar_layout.service import SolarService

        summary = SolarService(data).get_layout_summary(lay["result_id"])["summary"]
        surface, construction = build_surface(layout_req, summary["frame"])
        surface_path = tmp / "surface.json"
        surface_path.write_text(json.dumps(surface))
        construction["surface_json_bytes"] = surface_path.stat().st_size
        construction["surface_json_sha256"] = hashlib.sha256(surface_path.read_bytes()).hexdigest()
        del surface

        imp = phase("import", [surface_path, data], tmp / "import.json")
        assert imp["ok"], imp
        d = summary["dimensions"]
        W, D = d["table_width_W_m"], d["table_projected_depth_D_m"]
        request = {
            "schema_version": "solar.terrain.placement.request/1",
            "source_layout": {"result_id": lay["result_id"], "payload_digest": lay["payload_digest"]},
            "terrain": imp["terrain_id"],
            "placement": {"policy": "minimum_clearance_vertical_lift", "minimum_clearance_m": 0.5, "structure_depth_m": 0.1},
            "supports": {"model": "explicit_table_local", "points_ad_m": [[0.0, 0.0], [W / 2, 0.0], [W, 0.0], [0.0, D], [W / 2, D], [W, D]]},
            "limits": {"max_ground_slope_deg": 30.0, "max_support_above_ground_m": 10.0},
            "coverage": "mark_unknown_ground",
        }
        req_path = tmp / "request.json"
        req_path.write_text(json.dumps(request))
        place = phase("place", [req_path, data], tmp / "place.json")
        cold = phase("cold", [layout_path, surface_path, req_path, tmp / "cold-data"], tmp / "cold.json")

        counts = place.get("counts", {})
        td02 = {
            "requirement": "placement (independent verification and persistence included, layout and prepared terrain already stored) <= 30 s process wall time including interpreter start, and <= 1 GiB peak process-tree memory",
            "process_wall_s": place["wall_s"],
            "peak_tree_rss_mib": place["peak_tree_rss_mib"],
            "wall_target_s": WALL_TARGET_S,
            "memory_target_mib": MEMORY_TARGET_MIB,
            "all_tables_placed": counts.get("placed_tables") == counts.get("tables") == 364 and counts.get("placed_modules") == 10192,
            "verified": place.get("verification_ok") is True,
            "fresh_computation": place.get("reused") is False,
        }
        td02["pass"] = bool(place.get("ok") and td02["all_tables_placed"] and td02["verified"] and td02["fresh_computation"] and place["wall_s"] <= WALL_TARGET_S and place["peak_tree_rss_mib"] <= MEMORY_TARGET_MIB)
        report = {
            "schema": "solar.terrain.benchmarks/1",
            "gate": "TD02",
            "machine": machine(),
            "method": "fresh child process per phase; process-tree RSS (child and descendants) sampled every 10 ms with psutil; wall time from process start to exit, interpreter start included",
            "layout": {"fixture": str(layout_path.relative_to(ROOT)), "result_id": lay["result_id"], "module_count": lay["module_count"], "table_count": lay["table_count"]},
            "terrain_construction": construction,
            "placement_request": {k: v for k, v in request.items() if k not in ("source_layout", "terrain")},
            "phases": {"terrain_import": imp, "placement": place, "cold_workflow": cold},
            "td02": td02,
            "not_targets": "terrain import and the cold workflow have no T1 target; they are reported",
        }
        Path(out_path).write_text(json.dumps(report, indent=1) + "\n")
        print(json.dumps({"td02": td02, "import": {k: imp.get(k) for k in ("wall_s", "peak_tree_rss_mib")}, "cold": {k: cold.get(k) for k in ("wall_s", "peak_tree_rss_mib", "ok")}}, indent=1))
        return 0 if td02["pass"] else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
