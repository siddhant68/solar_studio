"""Module 02 T1 typed errors and limits: TC01, TC02, TC14 (fixture case T08).

Every rejected surface or request leaves nothing stored.
"""

from __future__ import annotations

import copy
import sqlite3
import sys

import pytest

from solar_layout.errors import DomainError
from terrain_helpers import ROOT, case, load, prepare, services


@pytest.fixture
def svcs(tmp_path):
    return services(tmp_path / "data")


def _count(ts, table: str) -> int:
    with sqlite3.connect(ts.store.db_path) as con:
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _nothing_stored(ts) -> None:
    for t in ("terrains", "terrain_arrays", "placements", "placement_tables", "placement_modules", "placement_supports"):
        assert _count(ts, t) == 0, t


def hill() -> dict:
    return load("surfaces/hill-fan.surface.json")


def _mut(fn):
    s = hill()
    fn(s)
    return s


SURFACE_CASES = [
    ("missing vertical datum", lambda s: s.pop("vertical"), "INVALID_TERRAIN", "vertical"),
    ("vertical without crs", lambda s: s.__setitem__("vertical", {"kind": "orthometric", "units": "m", "positive": "up"}), "INVALID_TERRAIN", "vertical"),
    ("degenerate triangle", lambda s: s["triangles"].__setitem__(0, [0, 1, 1]), "INVALID_TERRAIN", "triangles[0]"),
    ("overlapping triangles", lambda s: s["triangles"].append([0, 1, 2]), "INVALID_TERRAIN", "triangles[4]"),
    ("clockwise triangle", lambda s: s["triangles"].__setitem__(0, [0, 4, 1]), "INVALID_TERRAIN", "triangles[0]"),
    ("non-finite elevation", lambda s: s["vertices_xyz_m"][4].__setitem__(2, float("nan")), "INVALID_TERRAIN", "vertices_xyz_m[4][2]"),
    ("duplicate plan vertex", lambda s: s["vertices_xyz_m"].append([4.0, 4.0, 11.0]), "INVALID_TERRAIN", "vertices_xyz_m[5]"),
    ("index out of range", lambda s: s["triangles"].__setitem__(1, [1, 2, 9]), "INVALID_TERRAIN", "triangles[1]"),
    ("boolean coordinate", lambda s: s["vertices_xyz_m"][0].__setitem__(0, True), "INVALID_TERRAIN", "vertices_xyz_m[0][0]"),
    ("tiny triangle area", lambda s: (s["vertices_xyz_m"].extend([[10.0, 10.0, 1.0], [10.001, 10.0, 1.0], [10.0, 10.000001, 1.0]]), s["triangles"].append([5, 6, 7])), "INVALID_TERRAIN", "triangles[4]"),
    ("coordinate beyond envelope", lambda s: s["vertices_xyz_m"][0].__setitem__(0, 20_000_000.0), "RESOURCE_LIMIT", "vertices_xyz_m[0][0]"),
    ("elevation beyond envelope", lambda s: s["vertices_xyz_m"][4].__setitem__(2, 30_000.0), "RESOURCE_LIMIT", "vertices_xyz_m[4][2]"),
    ("integer beyond float range", lambda s: s["vertices_xyz_m"][0].__setitem__(1, 10**400), "RESOURCE_LIMIT", "vertices_xyz_m[0][1]"),
]


@pytest.mark.parametrize("name,mutate,code,field", SURFACE_CASES, ids=[c[0] for c in SURFACE_CASES])
def test_tc01_invalid_surfaces(svcs, name, mutate, code, field):
    _, ts = svcs
    with pytest.raises(DomainError) as ei:
        ts.import_terrain(_mut(mutate))
    assert ei.value.code == code, ei.value.to_dict()
    assert ei.value.field == field, ei.value.to_dict()
    v = ts.validate_terrain(_mut(mutate))
    assert v["valid"] is False and v["error"]["code"] == code
    _nothing_stored(ts)


def test_tc01_cracked_t_junction_rejected_consistent_accepted(svcs):
    _, ts = svcs
    with pytest.raises(DomainError) as ei:
        ts.import_terrain(load("surfaces/hill-fan-tjunction-cracked.surface.json"))
    e = ei.value.to_dict()
    assert e["code"] == "INVALID_TERRAIN" and e["details"]["reason"] == "t_junction_crack" and e["field"] == "vertices_xyz_m[5]"
    _nothing_stored(ts)
    ok = ts.import_terrain(load("surfaces/hill-fan-tjunction-consistent.surface.json"))
    assert ok["info"]["t_junction_count"] == 1


def test_tc14_count_limit_checked_before_geometric_work(svcs, monkeypatch):
    from solar_terrain import policy, surface

    _, ts = svcs
    monkeypatch.setattr(policy, "MAX_TRIANGLES", 3)

    def boom(*a, **k):
        raise AssertionError("geometric work started before the count limit was checked")

    monkeypatch.setattr(surface, "_orientation", boom)
    monkeypatch.setattr(surface, "_schema_check", boom)
    with pytest.raises(DomainError) as ei:
        ts.import_terrain(hill())
    assert ei.value.code == "RESOURCE_LIMIT" and ei.value.details["limit"] == "max_triangles"
    monkeypatch.setattr(policy, "MAX_TRIANGLES", 2_000_000)
    monkeypatch.setattr(policy, "MAX_VERTICES", 4)
    with pytest.raises(DomainError) as ei:
        ts.import_terrain(hill())
    assert ei.value.code == "RESOURCE_LIMIT" and ei.value.details["limit"] == "max_vertices"
    _nothing_stored(ts)


def test_tc14_limits_are_the_t1_values():
    from solar_terrain import policy

    assert policy.MAX_VERTICES == 1_000_000 and policy.MAX_TRIANGLES == 2_000_000
    assert policy.MAX_ABS_XY_M == 1e7 and policy.MAX_ABS_Z_M == 2e4
    assert policy.DEFAULT_TIMEOUT_S == 300.0


def test_tc14_placement_time_limit(svcs, monkeypatch):
    svc, ts = svcs
    c = case("T01")
    req = prepare(ts, svc, c)
    monkeypatch.setenv("SOLAR_TERRAIN_TIMEOUT_S", "0")
    with pytest.raises(DomainError) as ei:
        ts.place_on_terrain(req)
    assert ei.value.code == "RESOURCE_LIMIT" and ei.value.details["limit"] == "timeout_s"
    assert _count(ts, "placements") == 0 and _count(ts, "placement_tables") == 0
    monkeypatch.setenv("SOLAR_TERRAIN_TIMEOUT_S", "300")
    assert ts.place_on_terrain(req)["verification"]["ok"]


def test_tc14_import_time_limit(svcs, monkeypatch):
    _, ts = svcs
    monkeypatch.setenv("SOLAR_TERRAIN_TIMEOUT_S", "0")
    with pytest.raises(DomainError) as ei:
        ts.import_terrain(hill())
    assert ei.value.code == "RESOURCE_LIMIT"
    _nothing_stored(ts)


def _t03(ts, svc):
    return prepare(ts, svc, case("T03"))


def _t09(ts, svc):
    t09 = case("T09")
    lay = svc.generate_layout(request=load(t09["inputs"]["layout_request"]))
    ter = ts.import_terrain(load(t09["inputs"]["surface"]))
    req = copy.deepcopy(case("T03")["placement_request"])
    req["source_layout"] = {"result_id": lay["result_id"], "payload_digest": lay["payload_digest"]}
    req["terrain"] = ter["terrain_id"]
    return req


REQUEST_CASES = [
    ("frame mismatch", "t03", "frame", None, "FRAME_MISMATCH"),
    ("datum mismatch CRS", "t09", "expected_vertical", {"kind": "orthometric", "crs": "EPSG:5703"}, "DATUM_MISMATCH"),
    ("datum mismatch kind", "t09", "expected_vertical", {"kind": "ellipsoidal", "crs": "EPSG:5773"}, "DATUM_MISMATCH"),
    ("local benchmark mismatch", "t03", "expected_vertical", {"kind": "local", "id": "local:other-benchmark"}, "DATUM_MISMATCH"),
    ("empty expected_vertical", "t03", "expected_vertical", {}, "INVALID_INPUT"),
    ("partial expected_vertical", "t09", "expected_vertical", {"kind": "orthometric"}, "INVALID_INPUT"),
    ("local without id", "t03", "expected_vertical", {"kind": "local"}, "INVALID_INPUT"),
    ("source mismatch", "t03", "source_layout.payload_digest", "0" * 64, "SOURCE_MISMATCH"),
    ("unknown layout", "t03", "source_layout.result_id", "res_000000000000000000000000", "RESULT_NOT_FOUND"),
    ("unknown terrain", "t03", "terrain", "ter_000000000000000000000000", "TERRAIN_NOT_FOUND"),
    ("unsupported support model", "t03", "supports", {"model": "uniform_rows", "rows": 2}, "UNSUPPORTED_OPERATION"),
    ("unsupported policy", "t03", "placement.policy", "follow_terrain_reorientation", "UNSUPPORTED_OPERATION"),
    ("support outside footprint", "t03", "supports.points_ad_m", [[4.5, 1.0]], "INVALID_INPUT"),
    ("support at negative d", "t03", "supports.points_ad_m", [[1.0, -0.0001]], "INVALID_INPUT"),
    ("negative clearance", "t03", "placement.minimum_clearance_m", -0.1, "INVALID_INPUT"),
    ("slope limit zero", "t03", "limits.max_ground_slope_deg", 0, "INVALID_INPUT"),
    ("wrong coverage", "t03", "coverage", "interpolate", "INVALID_INPUT"),
    ("malformed terrain id", "t03", "terrain", "ter_xyz", "INVALID_INPUT"),
]


def _set(req: dict, path: str, value) -> None:
    keys = path.split(".")
    tgt = req
    for k in keys[:-1]:
        tgt = tgt[k]
    tgt[keys[-1]] = value


@pytest.mark.parametrize("name,base,path,value,code", REQUEST_CASES, ids=[c[0] for c in REQUEST_CASES])
def test_tc02_typed_request_errors(svcs, name, base, path, value, code):
    svc, ts = svcs
    req = _t03(ts, svc) if base == "t03" else _t09(ts, svc)
    if path == "frame":
        s = load("surfaces/hill-fan.surface.json")
        s["frame"]["id"] = "local:other-site"
        req["terrain"] = ts.import_terrain(s)["terrain_id"]
    else:
        _set(req, path, value)
    with pytest.raises(DomainError) as ei:
        ts.place_on_terrain(req)
    assert ei.value.code == code, ei.value.to_dict()
    assert _count(ts, "placements") == 0 and _count(ts, "placement_tables") == 0


def test_tc02_matching_expected_vertical_is_accepted(svcs):
    svc, ts = svcs
    req = _t09(ts, svc)
    plain = ts.place_on_terrain(req)
    req["expected_vertical"] = {"kind": "orthometric", "crs": "EPSG:5773"}
    asserted = ts.place_on_terrain(req)
    assert asserted["verification"]["ok"]
    assert asserted["placement_id"] != plain["placement_id"]
    assert asserted["summary"]["parameters_digest"] != plain["summary"]["parameters_digest"]
    from terrain_helpers import all_items

    a = all_items(ts, plain["placement_id"], "tables")
    b = all_items(ts, asserted["placement_id"], "tables")
    assert a == b
    local = _t03(ts, svc)
    local["expected_vertical"] = {"kind": "local", "id": "local:fixture-datum", "crs": None}
    assert ts.place_on_terrain(local)["verification"]["ok"]


def test_tc02_no_transformation_library_is_used(svcs):
    """No coordinate or datum transformation anywhere: no projection library is imported by
    the terrain package or loaded by a placement."""
    import ast

    svc, ts = svcs
    ts.place_on_terrain(_t09(ts, svc))
    assert "pyproj" not in sys.modules
    for path in (ROOT / "src" / "solar_terrain").glob("*.py"):
        tree = ast.parse(path.read_text())
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert not names & {"pyproj", "osgeo", "rasterio", "scipy"}, path.name


def test_non_finite_json_text_is_rejected_at_parse_time(tmp_path):
    """Through the CLI and HTTP the surface is JSON text: NaN is not valid JSON, so the parser
    rejects it (INVALID_INPUT) before validation; a non-finite value given through the Python
    API is INVALID_TERRAIN (TC01)."""
    from helpers_proc import cli

    p = tmp_path / "nan.surface.json"
    p.write_text('{"schema_version": "solar.terrain.surface/1", "vertices_xyz_m": [[0, 0, NaN]]}')
    rc, out, _ = cli(tmp_path / "data", "terrain", "validate", str(p))
    assert rc == 2 and out["error"]["code"] == "INVALID_INPUT"
