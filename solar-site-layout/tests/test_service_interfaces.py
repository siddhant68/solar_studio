"""S01, S03, S04, S05, S06, S07 and the result-selection policy."""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from conftest import FIXTURES, load_fixture
from helpers_proc import ROOT, big_request, cli
from solar_layout.errors import DomainError
from solar_layout.http_app import create_app
from solar_layout.service import SolarService


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def http(data_dir):
    with TestClient(create_app(str(data_dir))) as c:
        yield c


# ---- S01 / S03 ------------------------------------------------------------------------


def test_s01_cli_and_http_same_summary_and_identity(data_dir, http):
    rc, out, err = cli(data_dir, "generate", str(FIXTURES / "rectangle.request.json"))
    assert rc == 0, err
    cli_res = out["result"]
    r = http.post("/api/layouts", json={"request": load_fixture("rectangle.request.json")})
    assert r.status_code == 200
    http_res = r.json()
    assert cli_res["result_id"] == http_res["result_id"]
    assert cli_res["payload_digest"] == http_res["payload_digest"]
    assert cli_res["summary"]["quantities"] == http_res["summary"]["quantities"]
    assert http_res["reused_existing_result"] is True  # same store, same identity
    assert cli_res["summary"]["quantities"]["module_count"] == 24


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda r: r["frame"].__setitem__("units", "deg"), "UNSUPPORTED_FRAME"),
        (lambda r: r["placement"].__setitem__("row_pitch_m", 4.5), "INVALID_PITCH"),
        (lambda r: r["boundary"].__setitem__("coordinates", [[[0, 0], [12, 14], [12, 0], [0, 14], [0, 0]]]), "INVALID_GEOMETRY"),
        (lambda r: r.pop("frame"), "INVALID_INPUT"),
    ],
)
def test_s01_same_domain_errors(data_dir, http, tmp_path, mutate, code):
    req = load_fixture("rectangle.request.json")
    mutate(req)
    f = tmp_path / "bad.json"
    f.write_text(json.dumps(req))
    rc, out, _ = cli(data_dir, "generate", str(f))
    assert rc == 2 and out["ok"] is False and out["error"]["code"] == code
    r = http.post("/api/layouts", json={"request": req})
    assert r.status_code in (409, 413, 422) and r.json()["error"]["code"] == code
    assert r.json()["error"]["message"] == out["error"]["message"]


def test_s01_non_finite_json_over_http_is_typed(http):
    body = json.dumps({"request": load_fixture("rectangle.request.json")}).replace('"tilt_deg": 0.0', '"tilt_deg": NaN')
    r = http.post("/api/layouts", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_INPUT"


def test_s03_result_created_by_cli_read_by_http_and_python(data_dir, http):
    rc, out, _ = cli(data_dir, "project", "create", str(FIXTURES / "obstacle.request.json"), "--name", "Obstacle")
    pid = out["result"]["project_id"]
    rc, out, _ = cli(data_dir, "generate", "--project", pid)
    rid = out["result"]["result_id"]
    s = http.get(f"/api/layouts/{rid}", params={"project_id": pid}).json()
    assert s["summary"]["quantities"]["module_count"] == 20 and s["project_status"]["is_current"]
    items = http.get(f"/api/layouts/{rid}/items", params={"kind": "tables", "limit": 10}).json()
    assert [tuple(t["origin_xy_m"]) for t in items["items"]] == [(1.0, 1.0), (7.0, 1.0), (1.0, 6.0), (4.0, 6.0), (7.0, 6.0)]
    py = SolarService(data_dir).get_layout_summary(rid)
    assert py["payload_digest"] == s["payload_digest"]
    assert py["sources"][0]["interface"] == "cli"


# ---- selection policy -----------------------------------------------------------------


def test_selection_bound_to_source_revision(data_dir):
    svc = SolarService(data_dir)
    p = svc.create_project(load_fixture("rectangle.request.json"))
    r1 = svc.generate_layout(project_id=p["project_id"])
    assert r1["selection"] == "selected"
    req2 = load_fixture("rectangle.request.json")
    req2["perimeter_setback_m"] = 2.0
    p2 = svc.update_project(p["project_id"], 1, req2)
    assert p2["revision"] == 2 and p2["selected_result_id"] == r1["result_id"] and p2["selected_result_is_current"] is False
    st = svc.get_layout_summary(r1["result_id"], project_id=p["project_id"])["project_status"]
    assert st["is_current"] is False and st["label"].startswith("historical")
    # generating the OLD revision explicitly: allowed, but it cannot become the selection
    old = svc.generate_layout(project_id=p["project_id"], revision=1)
    assert old["selection"] == "historical_not_selected"
    r2 = svc.generate_layout(project_id=p["project_id"])
    assert r2["selection"] == "selected"
    assert svc.get_project(p["project_id"])["selected_result_id"] == r2["result_id"]
    # the generation never changed the editable specification
    assert svc.get_project(p["project_id"])["request"]["perimeter_setback_m"] == 2.0


# ---- S04 ------------------------------------------------------------------------------

RACE = r"""
import json, sys, time
from solar_layout.service import SolarService
from solar_layout.errors import DomainError
data_dir, pid, start, setback = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
req = json.load(open(sys.argv[5]))
req["perimeter_setback_m"] = setback
svc = SolarService(data_dir)
while time.time() < start:
    time.sleep(0.0005)
try:
    p = svc.update_project(pid, 1, req)
    print(json.dumps({"ok": True, "revision": p["revision"], "setback": setback}))
except DomainError as e:
    print(json.dumps({"ok": False, "code": e.code, "setback": setback}))
"""


def test_s04_two_processes_one_expected_revision(data_dir, tmp_path):
    svc = SolarService(data_dir)
    p = svc.create_project(load_fixture("rectangle.request.json"))
    script = tmp_path / "race.py"
    script.write_text(RACE)
    for attempt in range(3):
        if attempt:
            p = svc.create_project(load_fixture("rectangle.request.json"))
        start = time.time() + 1.5
        procs = [
            subprocess.Popen(
                [sys.executable, str(script), str(data_dir), p["project_id"], str(start), str(sb), str(FIXTURES / "rectangle.request.json")],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(ROOT),
            )
            for sb in (1.5, 2.5)
        ]
        outs = [json.loads(pr.communicate(timeout=60)[0]) for pr in procs]
        ok = [o for o in outs if o["ok"]]
        bad = [o for o in outs if not o["ok"]]
        assert len(ok) == 1 and len(bad) == 1, outs
        assert bad[0]["code"] == "REVISION_CONFLICT"
        final = svc.get_project(p["project_id"])
        assert final["revision"] == 2
        assert final["request"]["perimeter_setback_m"] == ok[0]["setback"]
        with sqlite3.connect(svc.store.db_path) as con:
            assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            revs = con.execute("SELECT revision FROM project_revisions WHERE project_id=? ORDER BY revision", (p["project_id"],)).fetchall()
        assert revs == [(1,), (2,)]


# ---- S05 ------------------------------------------------------------------------------


def test_s05_restart_reads_projects_results_pages_and_exports(data_dir):
    rc, out, _ = cli(data_dir, "project", "create", str(FIXTURES / "multipolygon.request.json"))
    pid = out["result"]["project_id"]
    rc, out, _ = cli(data_dir, "generate", "--project", pid)
    rid = out["result"]["result_id"]
    digest = out["result"]["payload_digest"]
    rc, out, _ = cli(data_dir, "export", rid, "--format", "csv")
    sha = out["result"]["sha256"]
    # a fresh process (restart) reads everything back
    rc, out, _ = cli(data_dir, "project", "get", pid)
    assert out["result"]["selected_result_id"] == rid
    rc, out, _ = cli(data_dir, "summary", rid)
    assert out["result"]["payload_digest"] == digest
    assert out["result"]["exports"][0]["sha256"] == sha
    rc, out, _ = cli(data_dir, "items", rid, "--kind", "modules", "--limit", "48")
    assert len(out["result"]["items"]) == 48 and out["result"]["next_cursor"] is None
    import hashlib

    from solar_layout.exports import verify_export_file

    f = verify_export_file(SolarService(data_dir).store, rid, "csv")
    assert hashlib.sha256(f.read_bytes()).hexdigest() == sha


@pytest.mark.parametrize("point", ["generate:modules_partially_written", "generate:before_commit"])
def test_s05_killed_generation_leaves_no_result(data_dir, tmp_path, point):
    req = big_request(4000)
    f = tmp_path / "big.json"
    f.write_text(json.dumps(req))
    rc, out, _ = cli(data_dir, "generate", str(f), env={"SOLAR_FAULT_POINT": point, "SOLAR_FAULT_MODE": "kill"}, check_json=False)
    assert rc == -9  # SIGKILL at the controlled write point
    svc = SolarService(data_dir)
    from solar_layout.validation import validate_layout_request
    from solar_layout.result import result_id_for

    rid = result_id_for(validate_layout_request(req).input_digest)
    with pytest.raises(DomainError) as e:
        svc.get_layout_summary(rid)
    assert e.value.code == "RESULT_NOT_FOUND"
    with sqlite3.connect(svc.store.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM layout_modules WHERE result_id=?", (rid,)).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM layout_tables WHERE result_id=?", (rid,)).fetchone()[0] == 0
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    # the same request then completes normally
    rc, out, _ = cli(data_dir, "generate", str(f))
    assert rc == 0 and out["result"]["result_id"] == rid and out["result"]["verification"]["ok"]


def test_s05_raised_fault_rolls_back(data_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_FAULT_POINT", "generate:before_result_row")
    monkeypatch.setenv("SOLAR_FAULT_MODE", "raise")
    svc = SolarService(data_dir)
    with pytest.raises(RuntimeError):
        svc.generate_layout(request=load_fixture("rectangle.request.json"))
    monkeypatch.delenv("SOLAR_FAULT_POINT")
    with sqlite3.connect(svc.store.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM layout_modules").fetchone()[0] == 0


def test_s05_killed_export_is_never_presented(data_dir, http):
    rc, out, _ = cli(data_dir, "generate", str(FIXTURES / "obstacle.request.json"))
    rid = out["result"]["result_id"]
    rc, out, _ = cli(data_dir, "export", rid, "--format", "json", env={"SOLAR_FAULT_POINT": "export:before_rename", "SOLAR_FAULT_MODE": "kill"}, check_json=False)
    assert rc == -9
    svc = SolarService(data_dir)
    assert svc.store.get_export(rid, "json") is None
    folder = Path(data_dir) / "exports" / rid
    assert not (folder / f"{rid}-layout.json").exists()
    assert any(p.name.endswith(".partial") for p in folder.iterdir())  # orphan, unreferenced
    assert all(e["format"] != "json" for e in svc.get_layout_summary(rid)["exports"])
    # the HTTP download path regenerates a complete, hashed file instead of serving the partial
    r = http.get(f"/api/layouts/{rid}/exports/json")
    assert r.status_code == 200 and json.loads(r.content)["result"]["result_id"] == rid
    import hashlib

    assert r.headers["x-content-sha256"] == hashlib.sha256(r.content).hexdigest()


# ---- S06 ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def large_result(tmp_path_factory):
    d = tmp_path_factory.mktemp("large") / "data"
    svc = SolarService(d)
    res = svc.generate_layout(request=big_request(10_000))
    return svc, res


def test_s06_cursor_paging_visits_every_item_once_in_order(large_result):
    svc, res = large_result
    total = res["items"]["modules"]["total"]
    assert total >= 10_000
    seen = []
    cursor = None
    pages = 0
    while True:
        page = svc.get_layout_items(res["result_id"], "modules", cursor=cursor, limit=500)
        assert len(page["items"]) <= 500
        seen.extend(m["seq"] for m in page["items"])
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == list(range(total)) and pages == -(-total // 500)
    ids = [m["module_id"] for m in svc.get_layout_items(res["result_id"], "modules", offset=0, limit=500)["items"]]
    assert len(set(ids)) == len(ids)
    default = svc.get_layout_items(res["result_id"], "tables")
    assert default["limit"] == 100 and len(default["items"]) == 100


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cursor": "not-a-cursor"},
        {"cursor": "eyJyIjoicmVzXzAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMCIsImsiOiJtb2R1bGVzIiwicyI6MX0"},
        {"offset": -1},
        {"offset": 10**9},
        {"limit": 0},
        {"limit": 501},
        {"offset": 0, "cursor": "x"},
    ],
)
def test_s06_invalid_cursor_and_range_are_typed(large_result, kwargs):
    svc, res = large_result
    with pytest.raises(DomainError) as e:
        svc.get_layout_items(res["result_id"], "modules", **kwargs)
    assert e.value.code == "INVALID_CURSOR"


def test_s06_cursor_from_other_kind_rejected(large_result):
    svc, res = large_result
    c = svc.get_layout_items(res["result_id"], "tables", limit=5)["next_cursor"]
    with pytest.raises(DomainError) as e:
        svc.get_layout_items(res["result_id"], "modules", cursor=c)
    assert e.value.code == "INVALID_CURSOR"


def test_s06_summary_and_page_reads_do_not_load_coordinates(large_result):
    svc, res = large_result
    rid = res["result_id"]
    with sqlite3.connect(svc.store.db_path) as con:
        full_bytes = con.execute("SELECT SUM(LENGTH(record_json)) FROM layout_modules WHERE result_id=?", (rid,)).fetchone()[0]
        plan = con.execute("EXPLAIN QUERY PLAN SELECT record_json FROM layout_modules WHERE result_id=? AND seq>=? ORDER BY seq LIMIT ?", (rid, 0, 100)).fetchall()
    assert any("USING INDEX" in str(r) or "PRIMARY KEY" in str(r) for r in plan)
    tracemalloc.start()
    svc.get_layout_summary(rid)
    _, peak_summary = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    svc.get_layout_items(rid, "modules", offset=5000, limit=100)
    _, peak_page = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert full_bytes > 2_000_000
    assert peak_summary < full_bytes / 10 and peak_page < full_bytes / 10
    out = Path(os.environ.get("SOLAR_EVIDENCE_DIR", "/nonexistent"))
    if out.is_dir():
        (out / "S06-memory.json").write_text(json.dumps({"result_id": rid, "module_count": res["items"]["modules"]["total"], "stored_module_record_bytes": full_bytes, "peak_bytes_summary_read": peak_summary, "peak_bytes_page_read_100": peak_page, "query_plan": [list(map(str, r)) for r in plan]}, indent=1))


# ---- S07 ------------------------------------------------------------------------------


@pytest.mark.parametrize("rid", ["../../etc/passwd", "res_../../x", "/etc/passwd", "res_" + "g" * 24, "", None, 5])
def test_s07_malformed_result_ids(data_dir, rid):
    svc = SolarService(data_dir)
    with pytest.raises(DomainError) as e:
        svc.export_layout(rid, "json")
    assert e.value.code == "RESULT_NOT_FOUND"


@pytest.mark.parametrize("fmt", ["../json", "json/../../x", "pdf", "", None, "JSON"])
def test_s07_malformed_formats(data_dir, fmt):
    svc = SolarService(data_dir)
    r = svc.generate_layout(request=load_fixture("rectangle.request.json"))
    with pytest.raises(DomainError) as e:
        svc.export_layout(r["result_id"], fmt)
    assert e.value.code == "INVALID_INPUT"


def test_s07_http_traversal_attempts(http):
    for url in ["/api/layouts/..%2F..%2Fetc%2Fpasswd/exports/json", "/api/layouts/res_000000000000000000000000/exports/..%2F..%2Fpasswd", "/static/../pyproject.toml"]:
        r = http.get(url)
        assert r.status_code in (400, 404, 422)
        assert b"[project]" not in r.content


def test_s07_symlinked_result_folder_cannot_escape(data_dir, tmp_path):
    svc = SolarService(data_dir)
    r = svc.generate_layout(request=load_fixture("rectangle.request.json"))
    outside = tmp_path / "outside"
    outside.mkdir()
    link = svc.store.export_root / r["result_id"]
    if link.exists():
        import shutil

        shutil.rmtree(link)
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(DomainError):
        svc.export_layout(r["result_id"], "csv")
    assert list(outside.iterdir()) == []


def test_s07_no_shell_interpolation_in_source():
    src = (ROOT / "src" / "solar_layout").rglob("*.py")
    for f in src:
        text = f.read_text()
        assert "shell=True" not in text, f
        assert "os.system(" not in text, f
        assert "os.popen(" not in text, f
