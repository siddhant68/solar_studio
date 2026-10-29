"""Module 02 T1 service and interfaces: TS01-TS05, TV03, TC12, TC13.

Separate OS processes are used where the gate is about processes: CLI parity, crashes at
fault points (SIGKILL), and byte-identical exports across processes and hash seeds.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import os
import re
import sqlite3
import subprocess
import sys

import pytest
from starlette.testclient import TestClient

from helpers_proc import big_request, cli
from solar_layout.errors import DomainError
from solar_layout.http_app import create_app
from terrain_helpers import FX, ROOT, all_items, case, grid_surface, layout_request, load, place_case, prepare, services, surface


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


def _files(tmp_path, c):
    lay = tmp_path / "layout.json"
    lay.write_text(json.dumps(layout_request(c)))
    sur = tmp_path / "surface.json"
    sur.write_text(json.dumps(surface(c)))
    req = tmp_path / "request.json"
    req.write_text(json.dumps(c["placement_request"]))
    return lay, sur, req


def _cli_place(tmp_path, data_dir, c, env=None):
    lay, sur, req = _files(tmp_path, c)
    rc, out, err = cli(data_dir, "generate", str(lay), env=env)
    assert rc == 0, err
    rc, ter, err = cli(data_dir, "terrain", "import", str(sur), env=env)
    assert rc == 0, err
    rc, pl, err = cli(data_dir, "terrain", "place", str(req), env=env)
    assert rc == 0, (err, pl)
    return ter["result"], pl["result"]


# ---- TS01: same identities and typed errors through CLI, HTTP and MCP -----------------------


def test_ts01_cli_http_mcp_same_identities_and_errors(tmp_path):
    from solar_layout.mcp_server import TERRAIN_TOOLS, _dispatch

    c = case("T03")
    ter_cli, pl_cli = _cli_place(tmp_path, tmp_path / "cli-data", c)

    with TestClient(create_app(str(tmp_path / "http-data"))) as http:
        assert http.post("/api/layouts", json={"request": layout_request(c)}).status_code == 200
        r = http.post("/api/terrains", json=surface(c))
        assert r.status_code == 200, r.text
        ter_http = r.json()
        r = http.post("/api/placements", json=c["placement_request"])
        assert r.status_code == 200, r.text
        pl_http = r.json()
        bad = copy.deepcopy(c["placement_request"])
        bad["expected_vertical"] = {"kind": "local", "id": "local:other-benchmark"}
        r_dm = http.post("/api/placements", json=bad)
        r_nf = http.get("/api/terrains/ter_000000000000000000000000")
        r_pnf = http.get("/api/placements/plc_000000000000000000000000")
        r_ex = http.get(f"/api/placements/{pl_http['placement_id']}/exports/csv")
        assert r_ex.status_code == 200 and len(r_ex.headers["x-content-sha256"]) == 64

    from solar_layout.service import SolarService
    from solar_terrain.service import TerrainService

    mdir = tmp_path / "mcp-data"
    svc = SolarService(mdir, interface="mcp")
    ts = TerrainService(svc, mdir, interface="mcp")
    assert set(TERRAIN_TOOLS) == {"validate_terrain", "import_terrain", "get_terrain", "place_on_terrain", "get_placement_summary", "get_placement_items", "export_placement", "verify_stored_placement"}
    _dispatch(svc, "generate_layout", {"request": layout_request(c)}, ts)
    ter_mcp = _dispatch(svc, "import_terrain", {"surface": surface(c)}, ts)
    pl_mcp = _dispatch(svc, "place_on_terrain", {"request": c["placement_request"]}, ts)

    assert ter_cli["terrain_id"] == ter_http["terrain_id"] == ter_mcp["terrain_id"] == c["placement_request"]["terrain"]
    assert pl_cli["placement_id"] == pl_http["placement_id"] == pl_mcp["placement_id"]
    assert pl_cli["payload_digest"] == pl_http["payload_digest"] == pl_mcp["payload_digest"]

    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps(bad))
    rc, out, _ = cli(tmp_path / "cli-data", "terrain", "place", str(bad_file))
    assert rc == 2 and out["error"]["code"] == "DATUM_MISMATCH"
    assert r_dm.status_code == 422 and r_dm.json()["error"]["code"] == "DATUM_MISMATCH"
    with pytest.raises(DomainError) as ei:
        _dispatch(svc, "place_on_terrain", {"request": bad}, ts)
    assert ei.value.code == "DATUM_MISMATCH"

    rc, out, _ = cli(tmp_path / "cli-data", "terrain", "get", "ter_000000000000000000000000")
    assert rc == 2 and out["error"]["code"] == "TERRAIN_NOT_FOUND"
    assert r_nf.status_code == 404 and r_nf.json()["error"]["code"] == "TERRAIN_NOT_FOUND"
    with pytest.raises(DomainError) as ei:
        _dispatch(svc, "get_terrain", {"terrain_id": "ter_000000000000000000000000"}, ts)
    assert ei.value.code == "TERRAIN_NOT_FOUND"
    assert r_pnf.status_code == 404 and r_pnf.json()["error"]["code"] == "PLACEMENT_NOT_FOUND"


def test_http_terrain_body_limit(data_dir, monkeypatch):
    import solar_layout.http_app as http_app

    monkeypatch.setattr(http_app, "MAX_TERRAIN_BODY_BYTES", 300)
    with TestClient(create_app(str(data_dir))) as http:
        r = http.post("/api/terrains", json=load("surfaces/void-ring.surface.json"))
        assert r.status_code == 413 and r.json()["error"]["code"] == "RESOURCE_LIMIT"
        r = http.post("/api/terrains/validate", content=b"x" * 2000, headers={"content-type": "application/json"})
        assert r.status_code == 413


# ---- TS02: paging ------------------------------------------------------------------------


def test_ts02_paging_is_bounded_stable_and_typed(data_dir):
    svc, ts = services(data_dir)
    _, out = place_case(ts, svc, "T01")
    pid = out["placement_id"]
    for kind, total in (("tables", 6), ("modules", 24), ("supports", 24)):
        by_offset = ts.get_placement_items(pid, kind, offset=0, limit=500)["items"]
        assert len(by_offset) == total
        seen, cursor, pages = [], None, 0
        while True:
            page = ts.get_placement_items(pid, kind, cursor=cursor, limit=5)
            assert len(page["items"]) <= 5 and page["total"] == total
            seen += page["items"]
            pages += 1
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert seen == by_offset and pages == -(-total // 5)
        assert [r["seq"] for r in seen] == list(range(total))
    cur = ts.get_placement_items(pid, "modules", limit=5)["next_cursor"]
    for kwargs in (
        {"kind": "modules", "cursor": "garbage"},
        {"kind": "tables", "cursor": cur},
        {"kind": "modules", "limit": 0},
        {"kind": "modules", "limit": 501},
        {"kind": "modules", "offset": 25},
        {"kind": "modules", "offset": -1},
        {"kind": "modules", "offset": 0, "cursor": cur},
    ):
        with pytest.raises(DomainError) as ei:
            ts.get_placement_items(pid, **kwargs)
        assert ei.value.code == "INVALID_CURSOR", kwargs
    with pytest.raises(DomainError) as ei:
        ts.get_placement_items(pid, "regions")
    assert ei.value.code == "INVALID_INPUT"
    _, other = place_case(ts, svc, "T03")
    with pytest.raises(DomainError) as ei:
        ts.get_placement_items(other["placement_id"], "modules", cursor=cur)
    assert ei.value.code == "INVALID_CURSOR"


def test_ts02_summary_reads_do_not_load_records(data_dir, monkeypatch):
    svc, ts = services(data_dir)
    _, out = place_case(ts, svc, "T01")

    def boom(*a, **k):
        raise AssertionError("a summary read loaded records")

    monkeypatch.setattr(ts.store, "page", boom)
    monkeypatch.setattr(ts.store, "iter_records", boom)
    monkeypatch.setattr(ts.store, "load_arrays", boom)
    s = ts.get_placement_summary(out["placement_id"])
    assert s["items"]["modules"]["total"] == 24 and s["verification"]["ok"]
    assert ts.get_terrain(out["terrain_id"])["info"]["triangle_count"] == 2


# ---- TS03: restart and interrupted writes -------------------------------------------------


def test_ts03_restart_reads_everything_back(data_dir):
    svc, ts = services(data_dir)
    _, out = place_case(ts, svc, "T05")
    pid = out["placement_id"]
    before = {k: all_items(ts, pid, k) for k in ("tables", "modules", "supports")}
    summary = ts.get_placement_summary(pid)
    svc2, ts2 = services(data_dir)
    assert ts2.get_placement_summary(pid) == summary
    assert {k: all_items(ts2, pid, k) for k in ("tables", "modules", "supports")} == before
    assert ts2.verify_stored_placement(pid)["ok"]
    again = ts2.place_on_terrain(case("T05")["placement_request"])
    assert again["reused_existing_placement"] is True and again["payload_digest"] == out["payload_digest"]


def _rows(db, *tables):
    with sqlite3.connect(db) as con:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


@pytest.mark.parametrize("point", ["terrain:arrays_partially_written", "terrain:before_row", "terrain:before_commit"])
def test_ts03_killed_terrain_import_leaves_nothing(tmp_path, data_dir, point):
    c = case("T03")
    _, sur, _ = _files(tmp_path, c)
    p = subprocess.run(
        [sys.executable, "-m", "solar_layout.cli", "--data-dir", str(data_dir), "terrain", "import", str(sur)],
        capture_output=True,
        text=True,
        env={**os.environ, "SOLAR_FAULT_POINT": point, "SOLAR_FAULT_MODE": "kill"},
        cwd=str(ROOT),
        timeout=120,
    )
    assert p.returncode == -9, (p.returncode, p.stdout, p.stderr)
    assert _rows(data_dir / "terrain.sqlite3", "terrains", "terrain_arrays") == {"terrains": 0, "terrain_arrays": 0}
    rc, out, err = cli(data_dir, "terrain", "import", str(sur))
    assert rc == 0 and out["result"]["reused_existing_terrain"] is False, err


def _big_case(tmp_path, data_dir):
    """A layout with more than 2,000 modules on a grid terrain, so record batches are
    flushed (and a fault point fires) before the placement row is written."""
    svc, ts = services(data_dir)
    lay = svc.generate_layout(request=big_request(2600))
    assert lay["summary"]["quantities"]["module_count"] > 2000
    tabs = []
    cursor = None
    while True:
        page = svc.get_layout_items(lay["result_id"], "tables", cursor=cursor, limit=500)
        tabs += page["items"]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    xs = [p[0] for t in tabs for p in t["footprint_xy_m"]]
    ys = [p[1] for t in tabs for p in t["footprint_xy_m"]]
    ter = ts.import_terrain(grid_surface(lay["summary"]["frame"], (min(xs) - 5, min(ys) - 5), (max(xs) + 5, max(ys) + 5), 61))
    d = lay["summary"]["dimensions"]
    req = {
        "schema_version": "solar.terrain.placement.request/1",
        "source_layout": {"result_id": lay["result_id"], "payload_digest": lay["payload_digest"]},
        "terrain": ter["terrain_id"],
        "placement": {"policy": "minimum_clearance_vertical_lift", "minimum_clearance_m": 0.5, "structure_depth_m": 0.1},
        "supports": {"model": "explicit_table_local", "points_ad_m": [[0.0, 0.0], [d["table_width_W_m"], d["table_projected_depth_D_m"]]]},
        "limits": {"max_ground_slope_deg": 30, "max_support_above_ground_m": 10},
        "coverage": "mark_unknown_ground",
    }
    path = tmp_path / "big-request.json"
    path.write_text(json.dumps(req))
    return path


@pytest.mark.parametrize("point", ["placement:records_partially_written", "placement:before_row", "placement:before_commit"])
def test_ts03_killed_placement_leaves_nothing(tmp_path, data_dir, point):
    req = _big_case(tmp_path, data_dir)
    p = subprocess.run(
        [sys.executable, "-m", "solar_layout.cli", "--data-dir", str(data_dir), "terrain", "place", str(req)],
        capture_output=True,
        text=True,
        env={**os.environ, "SOLAR_FAULT_POINT": point, "SOLAR_FAULT_MODE": "kill"},
        cwd=str(ROOT),
        timeout=300,
    )
    assert p.returncode == -9, (p.returncode, p.stdout, p.stderr)
    tables = ("placements", "placement_tables", "placement_modules", "placement_supports")
    assert _rows(data_dir / "terrain.sqlite3", *tables) == {t: 0 for t in tables}
    rc, out, err = cli(data_dir, "terrain", "place", str(req))
    assert rc == 0 and out["result"]["reused_existing_placement"] is False, err
    assert out["result"]["items"]["modules"]["total"] > 2000


# ---- TS04: provenance ---------------------------------------------------------------------


def test_ts04_provenance(data_dir):
    svc, ts = services(data_dir)
    _, out = place_case(ts, svc, "T03")
    prov = out["summary"]["provenance"]
    assert prov["algorithm_version"] == "terrain-vertical-lift/1" and prov["policy_version"] == "terrain-policy/1"
    assert prov["schema_version"] == "solar.terrain.placement.result/1"
    assert prov["software_version"]
    assert prov["source_commit"] is None or re.fullmatch(r"[0-9a-f]{40}", prov["source_commit"])
    for dep in ("python", "numpy", "shapely", "geos", "jsonschema"):
        assert prov["dependencies"][dep]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", prov["created_at"])
    assert out["summary"]["policy"]["numerical_policy"] == "terrain-policy/1"


# ---- TS05: real MCP client session ------------------------------------------------------------


def test_ts05_real_terrain_mcp_client_session(tmp_path):
    from test_browser_and_mcp import evidence_dir

    out = evidence_dir(tmp_path, "terrain-mcp")
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "terrain_mcp_session.py"), str(out), str(tmp_path / "mcp-data")], capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    assert p.returncode == 0, p.stdout + p.stderr
    steps = json.loads((out / "terrain-mcp-session-steps.json").read_text())["steps"]
    assert len(steps) >= 19 and all(s["ok"] for s in steps)
    names = [s["step"] for s in steps]
    assert any("DATUM_MISMATCH" in n for n in names)
    wire = [json.loads(line) for line in (out / "terrain-mcp-wire-transcript.jsonl").read_text().splitlines()]
    assert wire[0]["message"]["method"] == "initialize"
    called = {m["message"]["params"]["name"] for m in wire if m["dir"] == "client->server" and m["message"].get("method") == "tools/call"}
    assert {"import_terrain", "place_on_terrain", "get_placement_items", "export_placement"} <= called


# ---- TV03: exports ------------------------------------------------------------------------------


def test_tv03_exports_round_trip_every_record(data_dir):
    svc, ts = services(data_dir)
    _, out = place_case(ts, svc, "T01")
    pid = out["placement_id"]
    recs = {k: all_items(ts, pid, k) for k in ("tables", "modules", "supports")}
    root = ts.store.export_root
    js = ts.export_placement(pid, "json")
    doc = json.loads((root / js["path"]).read_text())
    assert doc["schema_version"] == "solar.terrain.placement.export/1"
    assert doc["result"] == ts.get_placement_summary(pid)["summary"]
    assert {k: doc[k] for k in recs} == recs
    mc = ts.export_placement(pid, "csv")
    rows = list(csv.DictReader(io.StringIO((root / mc["path"]).read_text())))
    assert len(rows) == len(recs["modules"])
    for row, m in zip(rows, recs["modules"]):
        assert (row["module_id"], row["table_id"]) == (m["module_id"], m["table_id"])
        for k, (x, y, z) in enumerate(m["corners_xyz_m"]):
            assert (float(row[f"c{k}_x_m"]), float(row[f"c{k}_y_m"]), float(row[f"c{k}_z_m"])) == (x, y, z)
    sc = ts.export_placement(pid, "supports_csv")
    rows = list(csv.DictReader(io.StringIO((root / sc["path"]).read_text())))
    assert len(rows) == len(recs["supports"])
    for row, s in zip(rows, recs["supports"]):
        assert row["support_id"] == s["support_id"] and row["table_id"] == s["table_id"]
        assert [float(row[k]) for k in ("a_m", "d_m", "x_m", "y_m", "ground_z_m", "top_z_m", "above_ground_m")] == [s["a_m"], s["d_m"], *s["xy_m"], s["ground_z_m"], s["top_z_m"], s["above_ground_m"]]


def test_tv03_exports_are_write_once_and_restored(data_dir):
    svc, ts = services(data_dir)
    _, out = place_case(ts, svc, "T03")
    pid = out["placement_id"]
    for fmt in ("json", "csv", "supports_csv"):
        a = ts.export_placement(pid, fmt)
        path = ts.store.export_root / a["path"]
        ino, data = path.stat().st_ino, path.read_bytes()
        b = ts.export_placement(pid, fmt)
        assert b == a and path.stat().st_ino == ino
        path.write_bytes(data + b"tampered")
        c = ts.export_placement(pid, fmt)
        assert c["sha256"] == a["sha256"] and path.read_bytes() == data
        path.unlink()
        assert ts.export_placement(pid, fmt)["sha256"] == a["sha256"] and path.read_bytes() == data
    assert len(ts.get_placement_summary(pid)["exports"]) == 3


def test_tv03_exports_identical_across_processes_and_hash_seeds(tmp_path):
    c = case("T05")
    results = []
    for seed in ("0", "4242"):
        d = tmp_path / f"seed-{seed}"
        env = {"PYTHONHASHSEED": seed}
        _, pl = _cli_place(tmp_path, d, c, env=env)
        files = {}
        for fmt in ("json", "csv", "supports_csv"):
            rc, out, err = cli(d, "terrain", "export", pl["placement_id"], "--format", fmt, env=env)
            assert rc == 0, err
            files[fmt] = open(out["result"]["absolute_path"], "rb").read()
        results.append((pl, files, d))
    (pa, fa, da), (pb, fb, db) = results
    assert pa["placement_id"] == pb["placement_id"] and pa["payload_digest"] == pb["payload_digest"]
    assert fa["csv"] == fb["csv"] and fa["supports_csv"] == fb["supports_csv"]
    # the JSON export carries the stored summary, whose provenance records when it was created
    ja, jb = json.loads(fa["json"]), json.loads(fb["json"])
    assert ja["result"]["provenance"]["created_at"] != jb["result"]["provenance"]["created_at"]
    stamp = re.compile(rb'"created_at":"[^"]*"')
    assert stamp.sub(b"", fa["json"]) == stamp.sub(b"", fb["json"])
    # within one store, a rebuild in another process with another hash seed gives the issued bytes
    rc, out, _ = cli(da, "terrain", "export", pa["placement_id"], "--format", "json", env={"PYTHONHASHSEED": "7"})
    path = out["result"]["absolute_path"]
    os.unlink(path)
    rc, out2, _ = cli(da, "terrain", "export", pa["placement_id"], "--format", "json", env={"PYTHONHASHSEED": "99"})
    assert rc == 0 and out2["result"]["sha256"] == out["result"]["sha256"]
    assert open(path, "rb").read() == fa["json"]


# ---- TC12: Module 01 is not modified ---------------------------------------------------------


@pytest.mark.parametrize("case_id", ["T01", "T03"])
def test_tc12_module01_results_and_exports_unchanged(data_dir, case_id):
    svc, ts = services(data_dir)
    c = case(case_id)
    lay = svc.generate_layout(request=layout_request(c))
    rid = lay["result_id"]
    issued = {}
    for fmt in ("json", "csv", "svg", "dxf", "report", "bundle"):
        meta = svc.export_layout(rid, fmt)
        path = svc.store.export_root / meta["path"]
        issued[fmt] = (meta["path"], meta["sha256"], path.stat().st_ino, path.read_bytes())
    summary = svc.get_layout_summary(rid)
    items = {k: svc.get_layout_items(rid, k, limit=500)["items"] for k in ("tables", "modules")}
    with sqlite3.connect(svc.store.db_path) as con:
        rows = con.execute("SELECT * FROM results").fetchall() + con.execute("SELECT * FROM layout_tables").fetchall() + con.execute("SELECT * FROM layout_modules").fetchall()

    ts.import_terrain(surface(c))
    out = ts.place_on_terrain(c["placement_request"])
    for fmt in ("json", "csv", "supports_csv"):
        ts.export_placement(out["placement_id"], fmt)
    ts.verify_stored_placement(out["placement_id"])

    assert svc.get_layout_summary(rid) == summary
    assert {k: svc.get_layout_items(rid, k, limit=500)["items"] for k in ("tables", "modules")} == items
    with sqlite3.connect(svc.store.db_path) as con:
        assert con.execute("SELECT * FROM results").fetchall() + con.execute("SELECT * FROM layout_tables").fetchall() + con.execute("SELECT * FROM layout_modules").fetchall() == rows
    for fmt, (path, sha, ino, data) in issued.items():
        meta = svc.export_layout(rid, fmt)
        p = svc.store.export_root / path
        assert (meta["path"], meta["sha256"], p.stat().st_ino, p.read_bytes()) == (path, sha, ino, data), fmt
    assert out["summary"]["source_layout"]["payload_digest"] == lay["payload_digest"]


# ---- TC13: identities ----------------------------------------------------------------------------


def test_tc13_terrain_identity(data_dir):
    _, ts = services(data_dir)
    base = load("surfaces/hill-fan.surface.json")
    first = ts.import_terrain(base)
    assert first["terrain_id"] == load("surfaces/INDEX.json")["hill-fan"]["terrain_id"]
    ints = copy.deepcopy(base)
    ints["vertices_xyz_m"] = [[int(c) if float(c).is_integer() else c for c in v] for v in ints["vertices_xyz_m"]]
    assert any(type(c) is int for v in ints["vertices_xyz_m"] for c in v)
    reordered = {k: base[k] for k in reversed(list(base))}
    renamed = copy.deepcopy(base)
    renamed["name"] = "another name"
    renamed["source"] = {"kind": "survey_tin", "provider": "someone else"}
    for doc in (ints, reordered, renamed):
        again = ts.import_terrain(doc)
        assert again["terrain_id"] == first["terrain_id"] and again["reused_existing_terrain"] is True
        assert again["name"] == base["name"]  # the stored row is kept
    changed = []
    g = copy.deepcopy(base)
    g["vertices_xyz_m"][4][2] = 10.6000001
    changed.append(g)
    d = copy.deepcopy(base)
    d["vertical"]["id"] = "local:another-datum"
    changed.append(d)
    f = copy.deepcopy(base)
    f["frame"]["crs"] = "EPSG:32633"
    changed.append(f)
    o = copy.deepcopy(base)
    o["triangles"] = o["triangles"][1:] + o["triangles"][:1]
    changed.append(o)
    ids = {ts.validate_terrain(doc)["terrain_id"] for doc in changed}
    assert len(ids) == 4 and first["terrain_id"] not in ids


def test_tc13_placement_identity(data_dir):
    svc, ts = services(data_dir)
    c = case("T03")
    req = prepare(ts, svc, c)
    first = ts.place_on_terrain(req)
    equivalent = json.loads(json.dumps(req))
    equivalent["placement"]["structure_depth_m"] = 0
    equivalent["supports"]["points_ad_m"] = [[int(a) if float(a).is_integer() else a, int(d) if float(d).is_integer() else d] for a, d in req["supports"]["points_ad_m"]]
    equivalent = {k: equivalent[k] for k in reversed(list(equivalent))}
    again = ts.place_on_terrain(equivalent)
    assert again["placement_id"] == first["placement_id"] and again["reused_existing_placement"] is True
    variants = []
    for path, value in (("placement.minimum_clearance_m", 0.6), ("placement.structure_depth_m", 0.1), ("limits.max_ground_slope_deg", 10.0), ("supports.points_ad_m", [[1.0, 1.0]])):
        v = copy.deepcopy(req)
        k1, k2 = path.split(".")
        v[k1][k2] = value
        variants.append(v)
    v = copy.deepcopy(req)
    v["expected_vertical"] = {"kind": "local", "id": "local:fixture-datum"}
    variants.append(v)
    ts.import_terrain(load("surfaces/hill-fan-tjunction-consistent.surface.json"))
    v = copy.deepcopy(req)
    v["terrain"] = load("surfaces/INDEX.json")["hill-fan-tjunction-consistent"]["terrain_id"]
    variants.append(v)
    other = svc.generate_layout(request=load(case("T13")["layout"]["request"]) | {"name": "renamed"})
    ids = {ts.place_on_terrain(v)["placement_id"] for v in variants}
    assert len(ids) == len(variants) and first["placement_id"] not in ids
    assert other["result_id"] == req["source_layout"]["result_id"]  # the layout name is not part of Module 01 identity
