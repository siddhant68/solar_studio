"""Regressions for the independent review of 26 October 2026 (reviews/module-01/2026-10-26).

F3 concurrent export collisions, F4 mutable export context and F5 verifier gaps are
reproduced here with the real interleavings: parallel service threads, a controlled
overlap inside the staging write, parallel HTTP requests against a live server, a second
project reusing an immutable result, and deliberately corrupted records. The browser
findings F1/F2 are covered by tests/browser/ui_checks.cjs (see test_browser_and_mcp.py).
"""

from __future__ import annotations

import concurrent.futures
import os
import copy
import hashlib
import io
import json
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pytest

import solar_layout.exports as ex
from conftest import load_fixture, run_layout
from helpers_proc import ROOT
from solar_layout.service import SolarService
from solar_layout.verify import verify_records

FORMATS = ("json", "csv", "svg", "dxf", "report", "bundle")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def svc_rid(tmp_path):
    svc = SolarService(tmp_path / "data")
    rid = svc.generate_layout(request=load_fixture("rectangle.request.json"))["result_id"]
    return svc, rid


# ---- F3: concurrent exports ----------------------------------------------------------


@pytest.mark.parametrize("fmt", FORMATS)
def test_f3_parallel_same_format_service_exports(svc_rid, fmt):
    svc, rid = svc_rid

    def call(_):
        return svc.export_layout(rid, fmt)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(call, range(24)))
    hashes = {r["sha256"] for r in results}
    assert len(hashes) == 1, "parallel exports of one immutable result must publish one identity"
    path = svc.store.export_root / results[0]["path"]
    assert sha(path.read_bytes()) == results[0]["sha256"]
    leftovers = [p.name for p in path.parent.iterdir() if p.name.endswith(".partial")]
    assert leftovers == []


def test_f3_controlled_overlap_inside_staging_write(svc_rid):
    """Both writers are inside their staging write at the same moment (reviewer's
    controlled interleaving); both must succeed and publish identical bytes."""
    svc, rid = svc_rid
    barrier = threading.Barrier(2)
    original = ex._write_staged

    def gated(path, writer, binary):
        def wait_then_write(handle):
            barrier.wait(timeout=10)
            writer(handle)

        return original(path, wait_then_write, binary)

    ex._write_staged = gated
    try:
        # bypass the publication lock so the two staging writes can really overlap
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futs = [pool.submit(ex._build_unlocked, svc.store, rid, "csv") for _ in range(2)]
            results = [f.result(timeout=30) for f in futs]
    finally:
        ex._write_staged = original
    assert results[0]["sha256"] == results[1]["sha256"]
    assert sha((svc.store.export_root / results[0]["path"]).read_bytes()) == results[0]["sha256"]


def test_f3_dxf_concurrency_does_not_touch_global_ezdxf_options(svc_rid):
    import ezdxf

    svc, rid = svc_rid
    before = ezdxf.options.write_fixed_meta_data_for_testing
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: svc.export_layout(rid, "dxf"), range(12)))
    assert len({r["sha256"] for r in results}) == 1
    assert ezdxf.options.write_fixed_meta_data_for_testing == before


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server(tmp_path):
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "solar_layout.cli", "--data-dir", str(tmp_path / "srv"), "serve", "--port", str(port)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    try:
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=20)


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _get(url: str) -> tuple[int, Any, bytes]:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.status, r.headers, r.read()  # case-insensitive header lookup


def test_f3_http_parallel_downloads_and_bundle_overlap(live_server):
    rid = _post(live_server + "/api/layouts", {"request": load_fixture("obstacle.request.json")})["result_id"]
    urls = [f"{live_server}/api/layouts/{rid}/exports/{fmt}" for fmt in ("csv",) * 24]
    urls += [f"{live_server}/api/layouts/{rid}/exports/{fmt}" for fmt in ("bundle", "json", "svg", "dxf", "report", "csv") * 4]
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        got = list(pool.map(_get, urls))
    by_fmt: dict[str, set] = {}
    for url, (status, headers, body) in zip(urls, got):
        assert status == 200
        assert headers["X-Content-SHA256"] == sha(body), url  # header describes the bytes downloaded
        by_fmt.setdefault(url.rsplit("/", 1)[1], set()).add(sha(body))
    assert all(len(v) == 1 for v in by_fmt.values()), by_fmt
    # the bundle's manifest describes exactly the standalone files
    bundle = next(body for url, (_, _, body) in zip(urls, got) if url.endswith("/bundle"))
    z = zipfile.ZipFile(io.BytesIO(bundle))
    manifest = json.loads(z.read("manifest.json"))
    for f in manifest["files"]:
        assert sha(z.read(f["name"])) == f["sha256"]
        assert {f["sha256"]} == by_fmt[f["format"]], f["format"]
    # POST (create) responses in parallel also agree with the download
    posts = [f"{live_server}/api/layouts/{rid}/exports/json"] * 12

    def post_export(url):
        return _post(url, {})

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        metas = list(pool.map(post_export, posts))
    assert {m["sha256"] for m in metas} == by_fmt["json"]


_EXPORT_ALL = """
import json, sys
from pathlib import Path
from solar_layout.service import SolarService
svc = SolarService(sys.argv[1])
out = {}
for name in ("rectangle", "obstacle", "hole"):
    req = json.loads((Path(sys.argv[2]) / f"{name}.request.json").read_text())
    rid = svc.generate_layout(request=req)["result_id"]  # reused: the copied store holds it
    out[name] = {fmt: svc.export_layout(rid, fmt)["sha256"] for fmt in ("json", "csv", "svg", "dxf", "report", "bundle")}
print(json.dumps(out))
"""


def test_exports_identical_across_processes_and_hash_seeds(tmp_path):
    """Found while repairing F3: ezdxf orders the DXF CLASSES section by iterating a set of
    type names, so DXF (and therefore bundle) bytes followed PYTHONHASHSEED and differed
    between processes. The same stored result must export to the same bytes in any
    process, or a rebuild could never match the issued file."""
    import shutil

    from conftest import FIXTURES

    seed_store = tmp_path / "seed"
    svc = SolarService(seed_store)
    for name in ("rectangle", "obstacle", "hole"):
        svc.generate_layout(request=load_fixture(f"{name}.request.json"))
    runs = []
    for seed in ("1", "4", "11"):
        data = tmp_path / f"d{seed}"
        data.mkdir()
        shutil.copy(seed_store / "solar.sqlite3", data / "solar.sqlite3")  # results only, no exports yet
        out = subprocess.run(
            [sys.executable, "-c", _EXPORT_ALL, str(data), str(FIXTURES)],
            cwd=str(ROOT), env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True, check=True, timeout=300,
        )
        runs.append(json.loads(out.stdout))
    assert runs[0] == runs[1] == runs[2]


# ---- F4: stable export context --------------------------------------------------------


def test_f4_result_export_unchanged_when_another_project_reuses_result(tmp_path):
    req = load_fixture("rectangle.request.json")
    svc = SolarService(tmp_path / "data")
    rid = svc.generate_layout(request=req)["result_id"]
    first = {fmt: svc.export_layout(rid, fmt) for fmt in FORMATS}
    first_bytes = {fmt: (svc.store.export_root / m["path"]).read_bytes() for fmt, m in first.items()}
    ctx1 = svc.export_layout(rid, "context")
    ctx1_bytes = (svc.store.export_root / ctx1["path"]).read_bytes()
    # another project, then a new revision of it, both reuse the same immutable result
    p = svc.create_project(req, name="Second project")
    assert svc.generate_layout(project_id=p["project_id"])["result_id"] == rid
    renamed = copy.deepcopy(req)
    renamed["name"] = "renamed only"
    p2 = svc.update_project(p["project_id"], 1, renamed)
    assert svc.generate_layout(project_id=p2["project_id"])["result_id"] == rid
    # restart the service on the same data
    svc2 = SolarService(tmp_path / "data")
    for fmt in FORMATS:
        again = svc2.export_layout(rid, fmt)
        assert again["path"] == first[fmt]["path"] and again["sha256"] == first[fmt]["sha256"], fmt
        assert (svc2.store.export_root / again["path"]).read_bytes() == first_bytes[fmt], fmt
    # project associations live in a separate, content-addressed context export:
    ctx2 = svc2.export_layout(rid, "context")
    assert ctx2["path"] != ctx1["path"] and ctx2["sha256"] != ctx1["sha256"]
    assert (svc2.store.export_root / ctx1["path"]).read_bytes() == ctx1_bytes  # previously issued file kept
    doc = json.loads((svc2.store.export_root / ctx2["path"]).read_bytes())
    assert {(s["project_id"], s["project_revision"]) for s in doc["project_sources"]} == {(p["project_id"], 1), (p["project_id"], 2)}
    assert doc["result_id"] == rid and doc["payload_digest"] == svc2.get_layout_summary(rid)["payload_digest"]


def test_f4_result_exports_contain_no_mutable_project_context(svc_rid):
    svc, rid = svc_rid
    doc = json.loads((svc.store.export_root / svc.export_layout(rid, "json")["path"]).read_bytes())
    assert "project_sources" not in doc
    assert doc["export"]["context"] == "result_only"


def test_f4_bundle_built_from_one_snapshot_matches_standalone_exports(svc_rid):
    svc, rid = svc_rid
    bundle = svc.export_layout(rid, "bundle")
    z = zipfile.ZipFile(svc.store.export_root / bundle["path"])
    manifest = json.loads(z.read("manifest.json"))
    for f in manifest["files"]:
        standalone = svc.export_layout(rid, f["format"])
        assert standalone["sha256"] == f["sha256"] == sha(z.read(f["name"]))


def test_f4_issued_export_is_never_rewritten_with_different_bytes(svc_rid):
    svc, rid = svc_rid
    meta = svc.export_layout(rid, "csv")
    path = svc.store.export_root / meta["path"]
    stat = path.stat()
    again = svc.export_layout(rid, "csv")
    assert again == meta
    assert path.stat().st_ino == stat.st_ino  # reused, not rebuilt


# ---- F5: verifier gaps ----------------------------------------------------------------


@pytest.fixture
def rect_records():
    val, comp, rr = run_layout(load_fixture("rectangle.request.json"))
    return val, rr, list(rr.table_records()), list(rr.module_records())


def failed(val, summary, tables, modules) -> set[str]:
    rep = verify_records(val.normalized, summary, tables, modules)
    return {k for k, v in rep["checks"].items() if not v["ok"]}


def test_f5_corrupt_module_power_is_detected(rect_records):
    val, rr, T, M = rect_records
    M2 = copy.deepcopy(M)
    M2[0]["power_wp"] = 123456
    bad = failed(val, rr.summary, T, M2)
    assert "record_fields" in bad and "record_totals" in bad


def test_f5_record_capacity_must_reconcile_with_summary(rect_records):
    val, rr, T, M = rect_records
    M2 = copy.deepcopy(M)
    for m in M2:
        m["power_wp"] = 600.0  # internally consistent records, inconsistent with request and summary
    assert {"record_fields", "record_totals"} <= failed(val, rr.summary, T, M2)


def test_f5_consistently_falsified_areas_are_detected(rect_records):
    val, rr, T, M = rect_records
    S = copy.deepcopy(rr.summary)
    q = S["quantities"]
    q["gross_site_area_m2"] = 999999.0
    q["buildable_area_m2"] = 999999.0
    q["buildable_area_bounds_m2"] = [999999.0, 999999.0]
    q["module_ground_coverage_gross"] = q["projected_module_area_m2"] / 999999.0
    q["module_ground_coverage_buildable"] = q["projected_module_area_m2"] / 999999.0
    assert "areas" in failed(val, S, T, M)


def test_f5_falsified_buildable_area_within_gross_is_detected(rect_records):
    val, rr, T, M = rect_records
    S = copy.deepcopy(rr.summary)
    q = S["quantities"]
    q["buildable_area_m2"] = 150.0  # true value 120, still below the 168 gross
    q["buildable_area_bounds_m2"] = [149.0, 151.0]
    q["module_ground_coverage_buildable"] = q["projected_module_area_m2"] / 150.0
    assert "areas" in failed(val, S, T, M)


@pytest.mark.parametrize("field,value", [("table_i", 7), ("row", 9), ("module_id", "T_j0_i0_r0_c0x"), ("table_id", "T_j0_i1")])
def test_f5_contract_fields_are_checked(rect_records, field, value):
    val, rr, T, M = rect_records
    M2 = copy.deepcopy(M)
    M2[3][field] = value
    assert failed(val, rr.summary, T, M2)


def test_f5_table_record_fields_are_checked(rect_records):
    val, rr, T, M = rect_records
    T2 = copy.deepcopy(T)
    T2[0]["module_count"] = 5
    T2[1]["upper_edge_z_m"] = 9.0
    assert "record_fields" in failed(val, rr.summary, T2, M)


def test_f5_payload_digest_integrity(rect_records):
    val, rr, T, M = rect_records
    S = copy.deepcopy(rr.summary)
    S["payload_digest"] = "0" * 64
    assert "payload_integrity" in failed(val, S, T, M)
    assert failed(val, rr.summary, T, M) == set()


def test_f5_new_checks_pass_on_all_fixture_results():
    for name in ("rectangle", "obstacle", "multipolygon", "concave-notch", "hole"):
        val, comp, rr = run_layout(load_fixture(f"{name}.request.json"))
        rep = verify_records(val.normalized, rr.summary, rr.table_records(), rr.module_records())
        assert rep["ok"], (name, {k for k, v in rep["checks"].items() if not v["ok"]})
        assert {"record_fields", "record_totals", "areas", "payload_integrity"} <= set(rep["checks"])
