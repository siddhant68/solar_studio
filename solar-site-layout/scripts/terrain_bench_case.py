"""One measured phase of the terrain benchmark, run in its own process by terrain_benchmark.py.

    python scripts/terrain_bench_case.py layout  LAYOUT.json DATA_DIR OUT.json
    python scripts/terrain_bench_case.py import  SURFACE.json DATA_DIR OUT.json
    python scripts/terrain_bench_case.py place   REQUEST.json DATA_DIR OUT.json
    python scripts/terrain_bench_case.py cold    LAYOUT.json SURFACE.json REQUEST.json DATA_DIR OUT.json

`place` and `cold` also time the engine, the independent verifier and persistence by
wrapping those service-level calls (the measured work is unchanged).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

T0 = time.perf_counter()

from solar_layout.errors import DomainError  # noqa: E402
from solar_layout.jsonio import loads_strict  # noqa: E402
from solar_layout.service import SolarService  # noqa: E402

import solar_terrain.service as tservice  # noqa: E402

IMPORTED = time.perf_counter()
STAGES: dict[str, float] = {}


def _timed(name, fn):
    def wrapper(*a, **k):
        t = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            STAGES[name] = STAGES.get(name, 0.0) + time.perf_counter() - t

    return wrapper


tservice.place = _timed("engine_s", tservice.place)
tservice.verify_placement = _timed("independent_verification_s", tservice.verify_placement)
tservice.load_source = _timed("load_layout_records_s", tservice.load_source)


def _services(data_dir: str):
    svc = SolarService(data_dir)
    ts = tservice.TerrainService(svc, data_dir)
    ts.store.insert_placement = _timed("persistence_s", ts.store.insert_placement)
    ts.store.load_arrays = _timed("load_terrain_arrays_s", ts.store.load_arrays)
    return svc, ts


def _read(path: str):
    return loads_strict(Path(path).read_bytes())


def main() -> int:
    cmd, *args = sys.argv[1:]
    out_path = Path(args[-1])
    res: dict = {"phase": cmd, "imports_s": IMPORTED - T0}
    try:
        t = time.perf_counter()
        if cmd == "layout":
            svc, _ = _services(args[1])
            lay = svc.generate_layout(request=_read(args[0]))
            res.update(result_id=lay["result_id"], payload_digest=lay["payload_digest"], module_count=lay["summary"]["quantities"]["module_count"], table_count=lay["summary"]["quantities"]["table_count"])
        elif cmd == "import":
            _, ts = _services(args[1])
            doc = _read(args[0])
            res["parse_s"] = time.perf_counter() - t
            ter = ts.import_terrain(doc)
            res.update(terrain_id=ter["terrain_id"], info=ter["info"], reused=ter["reused_existing_terrain"])
        elif cmd == "place":
            _, ts = _services(args[1])
            pl = ts.place_on_terrain(_read(args[0]))
            res.update(_placement(pl))
        elif cmd == "cold":
            svc, ts = _services(args[3])
            lay = svc.generate_layout(request=_read(args[0]))
            res["layout_s"] = time.perf_counter() - t
            t1 = time.perf_counter()
            ter = ts.import_terrain(_read(args[1]))
            res["import_s"] = time.perf_counter() - t1
            req = _read(args[2])
            assert req["source_layout"]["result_id"] == lay["result_id"] and req["terrain"] == ter["terrain_id"]
            t2 = time.perf_counter()
            pl = ts.place_on_terrain(req)
            res["place_s"] = time.perf_counter() - t2
            res.update(_placement(pl))
        else:
            raise SystemExit(f"unknown phase {cmd}")
        res["work_s"] = time.perf_counter() - t
        res["ok"] = True
    except DomainError as e:
        res.update(ok=False, error=e.to_dict())
    res["stages"] = STAGES
    out_path.write_text(json.dumps(res, indent=1))
    return 0 if res["ok"] else 1


def _placement(pl: dict) -> dict:
    s = pl["summary"]
    return {
        "placement_id": pl["placement_id"],
        "payload_digest": pl["payload_digest"],
        "reused": pl["reused_existing_placement"],
        "counts": s["counts"],
        "verification_ok": pl["verification"]["ok"],
        "engine_diagnostics": s["diagnostics"],
        "verifier_candidates": s["verification"]["candidates"],
        "verifier_exact_rational_evaluations": s["verification"]["exact_rational_evaluations"],
        "dependencies": s["provenance"]["dependencies"],
        "source_commit": s["provenance"]["source_commit"],
        "source_tree_dirty": s["provenance"]["source_tree_dirty"],
    }


if __name__ == "__main__":
    sys.exit(main())
