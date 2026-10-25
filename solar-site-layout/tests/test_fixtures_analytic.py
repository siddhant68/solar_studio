"""C02, C03, C07, C08 and the MultiPolygon fixture against independent expectations."""

from __future__ import annotations

import copy

import pytest

from conftest import load_fixture, run_layout
from independent import axis_aligned_expected_origins


def origins(rr):
    return [tuple(t["origin_xy_m"]) for t in rr.table_records()]


def test_c02_rectangle_exact_counts_areas_and_origins(rectangle):
    exp = load_fixture("rectangle.expected.json")
    independent = axis_aligned_expected_origins((0, 0, 12, 14), 1.0, (1.0, 1.0), 2.0, 4.0, 3.0, 5.0)
    assert sorted(independent) == sorted(map(tuple, exp["table_origins_xy_m"]))
    val, comp, rr = run_layout(rectangle)
    q = rr.summary["quantities"]
    d = rr.summary["dimensions"]
    assert q["table_count"] == exp["table_count"] == 6
    assert q["module_count"] == exp["module_count"] == 24
    assert q["dc_capacity_kwp"] == pytest.approx(13.2, abs=1e-9)
    assert q["gross_site_area_m2"] == pytest.approx(168, abs=1e-9)
    assert q["buildable_area_m2"] == pytest.approx(120, abs=1e-9)
    assert q["buildable_area_bounds_m2"][1] == pytest.approx(120, abs=1e-9)
    assert q["physical_module_area_m2"] == pytest.approx(48, abs=1e-9)
    assert q["projected_module_area_m2"] == pytest.approx(48, abs=1e-9)
    assert q["table_footprint_area_m2"] == pytest.approx(48, abs=1e-9)
    assert q["module_ground_coverage_gross"] == pytest.approx(exp["module_ground_coverage_gross"], abs=1e-12)
    assert q["module_ground_coverage_buildable"] == pytest.approx(0.4, abs=1e-12)
    assert d["table_width_W_m"] == 2 and d["table_slope_length_L_m"] == 4
    assert d["table_projected_depth_D_m"] == 4 and d["table_rise_H_m"] == 0
    got = origins(rr)
    assert len(got) == len(exp["table_origins_xy_m"])
    for o in exp["table_origins_xy_m"]:
        assert any(abs(o[0] - g[0]) <= 1e-9 and abs(o[1] - g[1]) <= 1e-9 for g in got), o
    assert rr.summary["z_kind"] == "relative_flat_datum"
    for m in rr.module_records():
        assert all(c[2] == pytest.approx(0.8, abs=1e-12) for c in m["corners_xyz_m"])
    assert rr.summary["placement"]["optimality"] == "fixed_lattice_no_search"
    assert len(rr.summary["placement"]["phase_candidates"]) == 1


def test_c03_obstacle_rejects_exactly_the_table_at_4_1(obstacle):
    exp = load_fixture("obstacle.expected.json")
    independent = axis_aligned_expected_origins((0, 0, 12, 14), 1.0, (1.0, 1.0), 2.0, 4.0, 3.0, 5.0, [(4, 1, 6, 5)])
    assert sorted(independent) == sorted(map(tuple, exp["table_origins_xy_m"]))
    val, comp, rr = run_layout(obstacle)
    q = rr.summary["quantities"]
    assert (q["table_count"], q["module_count"]) == (5, 20)
    assert q["dc_capacity_kwp"] == pytest.approx(11.0, abs=1e-9)
    assert q["buildable_area_m2"] == pytest.approx(112, abs=1e-9)
    assert q["gross_site_area_m2"] == pytest.approx(168, abs=1e-9)
    for key in ("physical_module_area_m2", "projected_module_area_m2", "table_footprint_area_m2"):
        assert q[key] == pytest.approx(40, abs=1e-9)
    assert sorted(origins(rr)) == sorted(map(tuple, exp["table_origins_xy_m"]))
    excl = [r for r in rr.summary["rejections"] if r["reason"].startswith("exclusion")]
    assert excl == [{"i": 1, "j": 0, "reason": "exclusion:EX-1"}]
    # whole tables are dropped: every remaining table has all 4 modules
    per = {}
    for m in rr.module_records():
        per[m["table_id"]] = per.get(m["table_id"], 0) + 1
    assert set(per.values()) == {4} and len(per) == 5


def test_obstacle_exact_tangency_is_allowed(obstacle):
    """An exclusion [3,4]x[1,6] lying exactly in the gap between table columns touches four
    tables (edges at x=3 and x=4, corners at y=6) without entering any interior."""
    req = copy.deepcopy(obstacle)
    req["exclusions"][0]["geometry"]["coordinates"] = [[[3, 1], [4, 1], [4, 6], [3, 6], [3, 1]]]
    _, _, rr = run_layout(req)
    assert sorted(origins(rr)) == [(1.0, 1.0), (1.0, 6.0), (4.0, 1.0), (4.0, 6.0), (7.0, 1.0), (7.0, 6.0)]


def test_multipolygon_all_components_considered():
    exp = load_fixture("multipolygon.expected.json")
    req = load_fixture("multipolygon.request.json")
    left = axis_aligned_expected_origins((0, 0, 12, 14), 1.0, (1.0, 1.0), 2.0, 4.0, 3.0, 5.0)
    right = axis_aligned_expected_origins((18, 0, 30, 14), 1.0, (1.0, 1.0), 2.0, 4.0, 3.0, 5.0)
    assert sorted(left + right) == sorted(map(tuple, exp["table_origins_xy_m"]))
    _, _, rr = run_layout(req)
    q = rr.summary["quantities"]
    assert (q["table_count"], q["module_count"]) == (12, 48)
    assert q["dc_capacity_kwp"] == pytest.approx(26.4, abs=1e-9)
    assert q["gross_site_area_m2"] == pytest.approx(336, abs=1e-9)
    assert q["buildable_area_m2"] == pytest.approx(240, abs=1e-9)
    assert sorted(origins(rr)) == sorted(map(tuple, exp["table_origins_xy_m"]))


@pytest.mark.parametrize("name", ["concave-notch.request.json", "hole.request.json"])
def test_c07_sampled_points_pass_but_footprint_is_rejected(name):
    adv = load_fixture("adversarial.expected.json")
    req = load_fixture(name)
    import shapely
    from shapely.geometry import Point, Polygon, shape

    site = shape(req["boundary"])
    fp = Polygon(adv["candidate_table_footprint_xy_m"])
    # the trap is real: corners and centre all lie inside the site ...
    samples = [Point(p) for p in adv["candidate_table_footprint_xy_m"][:4]] + [Point(adv["candidate_centre_xy_m"])]
    assert all(site.covers(p) for p in samples) == adv["corners_and_centre_inside_site"] is True
    # ... while the full footprint crosses forbidden ground
    assert not site.covers(fp) and adv["full_footprint_admissible"] is False
    _, comp, rr = run_layout(req)
    assert rr.summary["quantities"]["table_count"] == adv["expected_table_count"] == 0
    rejected = {(r["i"], r["j"]): r["reason"] for r in rr.summary["rejections"]}
    assert rejected[(0, 0)] == "outside_site"  # the (2,2) candidate is the lattice origin
    assert shapely.intersects(fp, site)


def test_corner_only_check_would_have_accepted_the_trap():
    """Guard against regressions to a sampled-point containment test."""
    from shapely.geometry import Point, shape

    adv = load_fixture("adversarial.expected.json")
    for name in adv["fixtures"]:
        site = shape(load_fixture(name)["boundary"])
        corners_ok = all(site.covers(Point(p)) for p in adv["candidate_table_footprint_xy_m"][:4])
        assert corners_ok, "fixture no longer exercises the corner-only trap"


def test_c08_large_setback_returns_successful_empty_layout(rectangle):
    req = copy.deepcopy(rectangle)
    req["perimeter_setback_m"] = 7.0  # 12 m wide site: nothing admissible
    _, comp, rr = run_layout(req)
    q = rr.summary["quantities"]
    assert (q["table_count"], q["module_count"], q["dc_capacity_kwp"]) == (0, 0, 0.0)
    assert q["buildable_area_m2"] == 0.0
    assert q["module_ground_coverage_buildable"] is None
    assert q["module_ground_coverage_gross"] == 0.0
    assert any("empty" in w for w in rr.summary["warnings"])


def test_c08_complete_exclusion_returns_empty_with_null_buildable_ratio(rectangle):
    req = copy.deepcopy(rectangle)
    req["exclusions"] = [{"id": "ALL", "geometry": copy.deepcopy(req["boundary"]), "keepout_m": 0.0}]
    _, _, rr = run_layout(req)
    q = rr.summary["quantities"]
    assert q["table_count"] == 0 and q["buildable_area_m2"] == 0.0
    assert q["module_ground_coverage_buildable"] is None
    assert q["gross_site_area_m2"] == pytest.approx(168)


def test_c08_multipolygon_components_each_contribute(rectangle):
    """Removing either component removes exactly its tables."""
    req = load_fixture("multipolygon.request.json")
    left_only = copy.deepcopy(req)
    left_only["boundary"] = {"type": "MultiPolygon", "coordinates": [req["boundary"]["coordinates"][0]]}
    _, _, rr_left = run_layout(left_only)
    _, _, rr_both = run_layout(req)
    assert rr_left.summary["quantities"]["table_count"] == 6
    assert rr_both.summary["quantities"]["table_count"] == 12
