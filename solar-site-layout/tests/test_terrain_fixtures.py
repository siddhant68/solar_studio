"""Module 02 T1 calculation gates on the analytic fixtures: TC03-TC10, TC18-TC21, TV01.

Expected numbers come from handoffs/module-02-terrain/fixtures/cases (closed forms,
re-derived independently by check_fixtures.py); the implementation must reproduce them.
"""

from __future__ import annotations

import copy
import math

import pytest

from solar_terrain.schemas import RESULT, validator
from terrain_helpers import NUMERIC_CASES, all_items, case, load, place_case, prepare, services

TOL_Z = 1e-9


def _close(a, b, tol):
    return abs(a - b) <= tol


@pytest.fixture
def svcs(tmp_path):
    return services(tmp_path / "data")


@pytest.mark.parametrize("case_id", NUMERIC_CASES)
def test_fixture_case_values(svcs, case_id):
    """TC03-TC09, TC18, TC19, TC21 (TC10 below): every expected table, support and total."""
    svc, ts = svcs
    c, out = place_case(ts, svc, case_id)
    pid = out["placement_id"]
    assert out["verification"]["ok"] is True
    tables = all_items(ts, pid, "tables")
    supports = all_items(ts, pid, "supports")
    modules = all_items(ts, pid, "modules")
    exp = c["expected"]
    assert [t["table_id"] for t in tables] == [t["table_id"] for t in exp["tables"]]
    for e, g in zip(exp["tables"], tables):
        tid = e["table_id"]
        assert g["status"] == e["status"], tid
        assert g["reasons"] == e["reasons"], tid
        assert g["footprint_xy_m"] == e["footprint_xy_m"], tid
        tol_a = 1e-12 if case_id == "T11" else 1e-9 * max(1.0, e["covered_area_m2"] + e["uncovered_area_m2"])
        assert _close(g["covered_area_m2"], e["covered_area_m2"], tol_a), (tid, g["covered_area_m2"])
        assert _close(g["uncovered_area_m2"], e["uncovered_area_m2"], tol_a), (tid, g["uncovered_area_m2"])
        if e["status"] == "unknown_ground":
            for k in ("lower_edge_z_m", "upper_edge_z_m", "vertical_lift_m", "min_clearance_m", "max_clearance_m", "max_ground_slope_deg", "mean_ground_gradient_uv", "min_clearance_at_xy_m"):
                assert k not in g, (tid, k)
            assert not [m for m in modules if m["table_id"] == tid]
            assert not [s for s in supports if s["table_id"] == tid]
            continue
        for k in ("lower_edge_z_m", "upper_edge_z_m", "vertical_lift_m", "min_clearance_m", "max_clearance_m"):
            if k in e:
                assert _close(g[k], e[k], TOL_Z), (tid, k, g[k], e[k])
        assert _close(g["max_ground_slope_deg"], e["max_ground_slope_deg"], 1e-9), (tid, g["max_ground_slope_deg"])
        if "min_clearance_at_xy_m" in e:
            assert g["min_clearance_at_xy_m"] == e["min_clearance_at_xy_m"], tid
        sup = [s for s in supports if s["table_id"] == tid]
        assert len(sup) == len(e["supports"])
        for k, (es, gs) in enumerate(zip(e["supports"], sup)):
            assert gs["support_id"] == f"S_{tid}_{k}"
            assert (gs["a_m"], gs["d_m"]) == (es["a_m"], es["d_m"])
            assert max(abs(gs["xy_m"][0] - es["xy_m"][0]), abs(gs["xy_m"][1] - es["xy_m"][1])) <= 1e-9
            for key in ("ground_z_m", "top_z_m", "above_ground_m"):
                assert _close(gs[key], es[key], TOL_Z), (tid, k, key, gs[key], es[key])
        mods = [m for m in modules if m["table_id"] == tid]
        assert len(mods) == (c["layout"]["modules_per_table"] if e["status"] == "placed" else 0)
    counts = out["summary"]["counts"]
    assert counts["placed_tables"] == exp["placed_tables"]
    assert counts["placed_modules"] == exp["placed_modules"]
    assert _close(counts["placed_dc_capacity_kwp"], exp["placed_dc_kwp"], 1e-9)


def test_tc05_interior_hill_is_not_missed_by_corner_sampling(svcs):
    svc, ts = svcs
    c, out = place_case(ts, svc, "T03")
    t = all_items(ts, out["placement_id"], "tables")[0]
    assert _close(t["lower_edge_z_m"], 11.1, TOL_Z)
    assert not _close(t["lower_edge_z_m"], c["must_not"]["corner_only_lower_edge_z_m"], 1e-3)
    assert t["min_clearance_at_xy_m"] == [4.0, 4.0]
    # corners: clearance 0.8 m (largest clearance on this flat table)
    assert _close(t["max_clearance_m"], c["expected"]["tables"][0]["clearance_at_footprint_corners_m"], TOL_Z)


def test_tc19_consistent_t_junction_gives_the_t03_placement(svcs):
    svc, ts = svcs
    _, t03 = place_case(ts, svc, "T03")
    _, t12 = place_case(ts, svc, "T12")
    a = all_items(ts, t03["placement_id"], "tables")[0]
    b = all_items(ts, t12["placement_id"], "tables")[0]
    for k in ("lower_edge_z_m", "upper_edge_z_m", "vertical_lift_m", "min_clearance_m", "max_clearance_m", "min_clearance_at_xy_m"):
        assert a[k] == b[k] or _close(a[k], b[k], TOL_Z), k
    assert ts.get_terrain(t12["terrain_id"])["info"]["t_junction_count"] == 1


def test_tc21_support_exactly_at_limit_and_just_above(svcs):
    svc, ts = svcs
    c, out = place_case(ts, svc, "T13")
    t = all_items(ts, out["placement_id"], "tables")[0]
    assert t["status"] == "placed" and t["reasons"] == []
    assert out["summary"]["diagnostics"]["exact_arithmetic"]["support_limit_exact_recomputations"] >= 1
    req = copy.deepcopy(c["placement_request"])
    req["limits"]["max_support_above_ground_m"] = 1.2499999999
    out2 = ts.place_on_terrain(req)
    t2 = all_items(ts, out2["placement_id"], "tables")[0]
    assert t2["status"] == "infeasible" and t2["reasons"] == ["support_above_ground_exceeds_limit"]
    assert out2["summary"]["diagnostics"]["exact_arithmetic"]["support_limit_exact_recomputations"] >= 1
    assert out2["summary"]["counts"]["placed_modules"] == 0 and out2["summary"]["counts"]["infeasible_tables"] == 1
    # infeasible keeps elevations and supports, has no modules
    assert _close(t2["lower_edge_z_m"], 23.0, TOL_Z)
    assert len(all_items(ts, out2["placement_id"], "supports")) == 4
    assert all_items(ts, out2["placement_id"], "modules") == []


def test_tc18_micro_gap_uncovered_area(svcs):
    svc, ts = svcs
    _, out = place_case(ts, svc, "T11")
    t = all_items(ts, out["placement_id"], "tables")[0]
    assert t["status"] == "unknown_ground"
    assert abs(t["uncovered_area_m2"] - 2 * (4.000001 - 4.0)) <= 1e-12
    assert t["uncovered_area_m2"] > 0


def test_tc10_rotated_and_translated_frame(svcs):
    svc, ts = svcs
    _, base = place_case(ts, svc, "T03")
    t09 = case("T09")
    lay = svc.generate_layout(request=load(t09["inputs"]["layout_request"]))
    assert lay["result_id"] == t09["inputs"]["observed_result_id"]
    assert lay["payload_digest"] == t09["inputs"]["observed_payload_digest"]
    ter = ts.import_terrain(load(t09["inputs"]["surface"]))
    assert ter["frame"]["crs"] == "EPSG:32633" and ter["vertical"]["crs"] == "EPSG:5773"
    req = copy.deepcopy(case("T03")["placement_request"])
    req["source_layout"] = {"result_id": lay["result_id"], "payload_digest": lay["payload_digest"]}
    req["terrain"] = ter["terrain_id"]
    out = ts.place_on_terrain(req)
    assert out["verification"]["ok"]
    a = all_items(ts, base["placement_id"], "tables")[0]
    b = all_items(ts, out["placement_id"], "tables")[0]
    assert a["table_id"] == b["table_id"] and a["status"] == b["status"]
    for k in ("lower_edge_z_m", "upper_edge_z_m", "vertical_lift_m", "min_clearance_m", "max_clearance_m"):
        assert _close(a[k], b[k], TOL_Z), k
    for p, q in zip(b["footprint_xy_m"], t09["expected_footprint_xy_m"]):
        assert max(abs(p[0] - q[0]), abs(p[1] - q[1])) <= 1e-6
    ang = math.radians(30.0)
    tx, ty = t09["transform"]["then_translate_xy_m"]

    def rot(p):
        return (p[0] * math.cos(ang) - p[1] * math.sin(ang) + tx, p[0] * math.sin(ang) + p[1] * math.cos(ang) + ty)

    rx, ry = rot(a["min_clearance_at_xy_m"])
    assert max(abs(rx - b["min_clearance_at_xy_m"][0]), abs(ry - b["min_clearance_at_xy_m"][1])) <= 1e-6
    sa = all_items(ts, base["placement_id"], "supports")
    sb = all_items(ts, out["placement_id"], "supports")
    assert [s["support_id"] for s in sa] == [s["support_id"] for s in sb]
    for s, r in zip(sa, sb):
        for k in ("ground_z_m", "top_z_m", "above_ground_m"):
            assert _close(s[k], r[k], TOL_Z)
        px, py = rot(s["xy_m"])
        assert max(abs(px - r["xy_m"][0]), abs(py - r["xy_m"][1])) <= 1e-6
    ma = all_items(ts, base["placement_id"], "modules")
    mb = all_items(ts, out["placement_id"], "modules")
    assert [m["module_id"] for m in ma] == [m["module_id"] for m in mb]
    for m, n in zip(ma, mb):
        for c1, c2 in zip(m["corners_xyz_m"], n["corners_xyz_m"]):
            assert _close(c1[2], c2[2], TOL_Z)
            x, y = rot(c1[:2])
            assert max(abs(x - c2[0]), abs(y - c2[1])) <= 1e-6


@pytest.mark.parametrize("case_id", NUMERIC_CASES)
def test_tc20_tc11_result_schema_and_status_records(svcs, case_id):
    """Every summary and record validates against the final result schema (full JSON Schema
    validator, every record); fixed contract fields."""
    svc, ts = svcs
    _, out = place_case(ts, svc, case_id)
    pid = out["placement_id"]
    summary = out["summary"]
    errors = list(validator(RESULT).iter_errors(summary))
    assert not errors, [e.message for e in errors]
    for kind, definition in (("tables", "table_record"), ("modules", "module_record"), ("supports", "support_record")):
        v = validator(RESULT, definition)
        for rec in all_items(ts, pid, kind):
            errs = list(v.iter_errors(rec))
            assert not errs, (kind, rec.get("seq"), [e.message for e in errs])
    assert summary["z_kind"] == "terrain_vertical_reference"
    assert summary["not_computed"] == ["embedment_depth", "pile_length", "foundation_design", "structural_adequacy", "grading", "cut_fill", "drainage"]
    keys = set()
    for kind in ("tables", "modules", "supports"):
        for rec in all_items(ts, pid, kind):
            keys |= set(rec)
    assert not [k for k in keys if "pile" in k or "embed" in k or "foundation" in k]
    tables = all_items(ts, pid, "tables")
    for t in tables:
        if t["status"] == "infeasible":
            assert t["reasons"] and set(t["reasons"]) <= {"ground_slope_exceeds_limit", "support_above_ground_exceeds_limit"}
    c = summary["counts"]
    assert c["tables"] == c["placed_tables"] + c["unknown_ground_tables"] + c["infeasible_tables"]


@pytest.mark.parametrize("case_id", NUMERIC_CASES)
def test_tv01_verifier_passes_and_reports_its_candidates(svcs, case_id):
    svc, ts = svcs
    _, out = place_case(ts, svc, case_id)
    ver = out["summary"]["verification"]
    assert ver["ok"] and all(v["ok"] for v in ver["checks"].values())
    assert ver["candidates"]["method"] == "uniform grid over triangle bounding boxes"
    assert ver["candidates"]["candidate_triangles_total"] >= 1
    again = ts.verify_stored_placement(out["placement_id"])
    assert again["ok"], {k: v["failures"] for k, v in again["checks"].items() if not v["ok"]}
    diag = out["summary"]["diagnostics"]
    assert diag["candidate_triangles_total"] >= 1 and "exact_arithmetic" in diag


def test_tv01_candidate_selection_is_bounded(tmp_path):
    """On a 200 x 200 m, 80,000-triangle grid the engine and the verifier each examine only
    triangles near each footprint, not the whole surface."""
    from terrain_helpers import grid_surface

    svc, ts = services(tmp_path / "data")
    c = case("T01")
    lay = svc.generate_layout(request=load(c["layout"]["request"]))
    surf = grid_surface(lay["summary"]["frame"], (-100.0, -100.0), (100.0, 100.0), 201)
    ter = ts.import_terrain(surf)
    req = copy.deepcopy(c["placement_request"])
    req["terrain"] = ter["terrain_id"]
    out = ts.place_on_terrain(req)
    assert out["summary"]["counts"]["placed_tables"] == 6
    diag = out["summary"]["diagnostics"]
    cand = out["summary"]["verification"]["candidates"]
    # a 2 x 4 m footprint over 1 m cells touches at most 4 x 6 cells = 48 triangles (+ rounding)
    assert diag["candidate_triangles_max_per_table"] <= 60, diag
    assert cand["candidate_triangles_max_per_table"] <= 60, cand
    assert diag["candidate_triangles_total"] < 0.01 * 80_000
    assert cand["candidate_triangles_total"] < 0.01 * 80_000
