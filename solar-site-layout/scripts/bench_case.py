"""One benchmark run in a fresh process (driven by scripts/benchmark.py).

    python scripts/bench_case.py generate FIXTURE DATA_DIR OUT.json
    python scripts/bench_case.py export RESULT_ID DATA_DIR OUT.json

`generate` times validation, layout computation, record building, independent
verification and the persisting transaction separately, using the same functions as
SolarService.generate_layout. `export` times each export format on a stored result.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from solar_layout.errors import DomainError
from solar_layout.layout import compute_layout
from solar_layout.result import ResultRecords
from solar_layout.service import SolarService
from solar_layout.store import now
from solar_layout.validation import validate_layout_request
from solar_layout.verify import verify_records


def generate(fixture: str, data_dir: str) -> dict:
    req = json.loads(Path(fixture).read_text())
    svc = SolarService(data_dir, interface="benchmark")
    t = {}
    t0 = time.perf_counter()
    try:
        val = validate_layout_request(req)
        t["validate_s"] = time.perf_counter() - t0
        t1 = time.perf_counter()
        comp = compute_layout(val)
        t["compute_s"] = time.perf_counter() - t1
    except DomainError as e:
        return {"ok": False, "error": e.to_dict(), "elapsed_s": time.perf_counter() - t0, "stored_results": _count(svc)}
    t2 = time.perf_counter()
    rr = ResultRecords(comp)
    tables = list(rr.table_records())
    t["records_and_digest_s"] = time.perf_counter() - t2
    t3 = time.perf_counter()
    ver = verify_records(val.normalized, rr.summary, tables, rr.module_records())
    t["verify_s"] = time.perf_counter() - t3
    t4 = time.perf_counter()
    created = now()
    svc.store.insert_result(rr.result_id, val.input_digest, rr.payload_digest, val.normalized, rr.summary, rr.region_geojson(), svc.provenance(created), ver, tables, rr.module_records(), created)
    t["persist_s"] = time.perf_counter() - t4
    t["generate_and_verify_total_s"] = time.perf_counter() - t0
    q = rr.summary["quantities"]
    return {"ok": ver["ok"], "result_id": rr.result_id, "module_count": q["module_count"], "table_count": q["table_count"], "dc_capacity_kwp": q["dc_capacity_kwp"], "candidates_evaluated": comp.diagnostics["candidates_evaluated"], "timings": t}


def _count(svc: SolarService) -> int:
    import sqlite3

    with sqlite3.connect(svc.store.db_path) as con:
        return con.execute("SELECT COUNT(*) FROM results").fetchone()[0]


def export(result_id: str, data_dir: str) -> dict:
    svc = SolarService(data_dir, interface="benchmark")
    out = {}
    for fmt in ("json", "csv", "svg", "dxf", "report", "bundle"):
        t0 = time.perf_counter()
        meta = svc.export_layout(result_id, fmt)
        out[fmt] = {"seconds": time.perf_counter() - t0, "bytes": meta["bytes"], "sha256": meta["sha256"]}
    return {"ok": True, "exports": out}


if __name__ == "__main__":
    mode, arg, data_dir, out_path = sys.argv[1:5]
    res = generate(arg, data_dir) if mode == "generate" else export(arg, data_dir)
    Path(out_path).write_text(json.dumps(res, indent=1))
