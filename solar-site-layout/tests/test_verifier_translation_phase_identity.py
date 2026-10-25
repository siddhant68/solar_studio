"""C10 (verifier catches corruption), C11 (translation matrix), C13 (phase search),
C14 (identity and digests)."""

from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from conftest import load_fixture, run_layout, shifted
from solar_layout.verify import verify_records


def verified(val, rr, tables=None, modules=None, summary=None):
    rep = verify_records(
        val.normalized,
        summary or rr.summary,
        tables if tables is not None else list(rr.table_records()),
        modules if modules is not None else list(rr.module_records()),
    )
    return rep["ok"], {k for k, v in rep["checks"].items() if not v["ok"]}


# ---- C10 ------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["rectangle", "obstacle", "multipolygon", "concave-notch", "hole"])
def test_c10_fixture_results_verify(name):
    val, _, rr = run_layout(load_fixture(f"{name}.request.json"))
    ok, failed = verified(val, rr)
    assert ok, failed


def test_c10_tables_and_modules_do_not_overlap_and_totals_agree(obstacle):
    val, _, rr = run_layout(obstacle)
    T = list(rr.table_records())
    M = list(rr.module_records())
    assert len({m["module_id"] for m in M}) == len(M) == 20
    owners = {}
    for m in M:
        owners.setdefault(m["module_id"], set()).add(m["table_id"])
    assert all(len(v) == 1 for v in owners.values())
    assert sum(t["module_count"] for t in T) == len(M) == rr.summary["quantities"]["module_count"]


@pytest.fixture
def obstacle_result(obstacle):
    val, _, rr = run_layout(obstacle)
    return val, rr, list(rr.table_records()), list(rr.module_records())


def test_c10_detects_table_moved_into_exclusion(obstacle_result):
    val, rr, T, M = obstacle_result
    T2 = copy.deepcopy(T)
    T2[0].update(origin_xy_m=[4.0, 1.0], footprint_xy_m=[[4, 1], [6, 1], [6, 5], [4, 5]], i=1)
    ok, failed = verified(val, rr, T2, M)
    assert not ok and "exclusions" in failed


def test_c10_detects_moved_module(obstacle_result):
    val, rr, T, M = obstacle_result
    M2 = copy.deepcopy(M)
    M2[5]["corners_xyz_m"][2][0] += 0.3
    ok, failed = verified(val, rr, T, M2)
    assert not ok and "module_geometry" in failed


def test_c10_detects_wrong_relative_height(obstacle_result):
    val, rr, T, M = obstacle_result
    M2 = copy.deepcopy(M)
    M2[0]["corners_xyz_m"][0][2] = 0.0
    assert "module_geometry" in verified(val, rr, T, M2)[1]


def test_c10_detects_dropped_and_orphan_modules(obstacle_result):
    val, rr, T, M = obstacle_result
    assert {"quantities", "identity_and_membership"} <= verified(val, rr, T, M[:-1])[1]
    M2 = copy.deepcopy(M)
    M2[0]["table_id"] = "T_j9_i9"
    assert "identity_and_membership" in verified(val, rr, T, M2)[1]


def test_c10_detects_duplicate_and_overlapping_tables(obstacle_result):
    val, rr, T, M = obstacle_result
    failed = verified(val, rr, T + [copy.deepcopy(T[0])], M)[1]
    assert {"identity_and_membership", "tables_disjoint"} <= failed
    T2 = copy.deepcopy(T)
    # shift the (7,1) table half a metre west so it overlaps nothing but breaks the lattice
    T2[1]["origin_xy_m"] = [6.5, 1.0]
    T2[1]["footprint_xy_m"] = [[6.5, 1], [8.5, 1], [8.5, 5], [6.5, 5]]
    assert "lattice_positions" in verified(val, rr, T2, M)[1]


def test_c10_detects_capacity_and_area_tampering(obstacle_result):
    val, rr, T, M = obstacle_result
    S = copy.deepcopy(rr.summary)
    S["quantities"]["dc_capacity_kwp"] = 13.2
    assert "quantities" in verified(val, rr, T, M, S)[1]
    S = copy.deepcopy(rr.summary)
    S["quantities"]["module_ground_coverage_buildable"] = None
    assert "quantities" in verified(val, rr, T, M, S)[1]


def test_c10_detects_table_across_hole_and_outside_setback():
    req = load_fixture("hole.request.json")
    val, _, rr = run_layout(req)
    S = copy.deepcopy(rr.summary)
    S["quantities"].update(table_count=1, module_count=4, dc_capacity_kwp=2.2, physical_module_area_m2=16.0, projected_module_area_m2=16.0, table_footprint_area_m2=16.0)
    S["quantities"]["module_ground_coverage_gross"] = 16.0 / S["quantities"]["gross_site_area_m2"]
    S["quantities"]["module_ground_coverage_buildable"] = 16.0 / S["quantities"]["buildable_area_m2"]
    T = [{"seq": 0, "table_id": "T_j0_i0", "i": 0, "j": 0, "origin_xy_m": [2.0, 2.0], "footprint_xy_m": [[2, 2], [6, 2], [6, 6], [2, 6]], "module_count": 4}]
    M = []
    for r in range(2):
        for c in range(2):
            a0, b0 = 2 * c, 2 * r
            M.append({"module_id": f"T_j0_i0_r{r}_c{c}", "table_id": "T_j0_i0", "row": r, "column": c,
                      "corners_xyz_m": [[2 + a0, 2 + b0, 0.8], [4 + a0, 2 + b0, 0.8], [4 + a0, 4 + b0, 0.8], [2 + a0, 4 + b0, 0.8]]})
    ok, failed = verified(val, rr, T, M, S)
    assert not ok and failed == {"site_containment"}


# ---- C11 ------------------------------------------------------------------------------


def test_c11_translation_matrix_21_pairs():
    tm = load_fixture("translation-matrix.json")
    base = load_fixture(tm["seed_fixture"])
    pairs = 0
    for az in tm["azimuths_deg"]:
        r0 = copy.deepcopy(base)
        r0["table"]["facing_azimuth_deg"] = az
        _, _, rr0 = run_layout(r0)
        mem0 = [(t["i"], t["j"]) for t in rr0.table_records()]
        c0 = np.array([m["corners_xyz_m"] for m in rr0.module_records()])
        for dx, dy in tm["translation_offsets_m"]:
            val, _, rr = run_layout(shifted(r0, dx, dy))
            mem = [(t["i"], t["j"]) for t in rr.table_records()]
            assert mem == mem0, (az, dx, dy)
            assert rr.summary["quantities"]["module_count"] == rr0.summary["quantities"]["module_count"]
            c = np.array([m["corners_xyz_m"] for m in rr.module_records()])
            if c.size:
                back = c.copy()
                back[..., 0] -= dx
                back[..., 1] -= dy
                assert np.abs(back - c0).max() <= 1e-6
            assert verify_records(val.normalized, rr.summary, rr.table_records(), rr.module_records())["ok"]
            pairs += 1
    assert pairs == tm["comparisons"] == 21


def test_c11_rotated_projected_frame_regression():
    """Projected-coordinate site, azimuth 197, phase search, keepout, hole: stable and verified."""
    req = load_fixture("obstacle.request.json")
    req = shifted(req, 446_000.0, 4_412_000.0)
    req["frame"] = {"kind": "projected_cartesian", "id": "utm33n", "crs": "EPSG:32633", "units": "m", "axes": {"x": "east", "y": "north"}}
    req["table"]["facing_azimuth_deg"] = 197.0
    req["exclusions"][0]["keepout_m"] = 0.75
    val, _, rr = run_layout(req)
    _, _, rr_local = run_layout(shifted(req, -446_000.0, -4_412_000.0) | {"frame": load_fixture("obstacle.request.json")["frame"]})
    assert [(t["i"], t["j"]) for t in rr.table_records()] == [(t["i"], t["j"]) for t in rr_local.table_records()]
    assert verify_records(val.normalized, rr.summary, rr.table_records(), rr.module_records())["ok"]
    assert rr.summary["frame"]["crs"] == "EPSG:32633"


# ---- C13 ------------------------------------------------------------------------------


def phase_request():
    req = load_fixture("rectangle.request.json")
    req["boundary"]["coordinates"] = [[[0, 0], [13.5, 0], [13.5, 15.5], [0, 15.5], [0, 0]]]
    req["perimeter_setback_m"] = 0.0
    req["placement"]["mode"] = "phase_search_3x3"
    req["placement"]["anchor_xy_m"] = [-0.5, -0.5]
    return req


def test_c13_nine_candidates_selection_and_labels():
    req = phase_request()
    _, comp, rr = run_layout(req)
    pl = rr.summary["placement"]
    scores = pl["phase_candidates"]
    assert [tuple(s["phase_index"]) for s in scores] == [(p, q) for p in range(3) for q in range(3)]
    assert scores[0]["phase_index"] == [0, 0] and scores[0]["offset_u_m"] == 0.0 and scores[0]["offset_v_m"] == 0.0
    best = max(s["module_count"] for s in scores)
    sel = [s for s in scores if s["phase_index"] == pl["selected_phase_index"]][0]
    assert sel["module_count"] == best >= scores[0]["module_count"]
    first_best = next(s for s in scores if s["module_count"] == best)
    assert sel["phase_index"] == first_best["phase_index"]  # stable tie-break
    assert pl["optimality"] == "best_of_evaluated_candidates"
    assert "3x3" in pl["search_scope"]
    assert rr.summary["quantities"]["module_count"] == best
    # independently: zero phase from anchor (-0.5,-0.5) on [0,13.5]x[0,15.5] fits x in {2.5,5.5,8.5}+..., check >= by intervals
    from independent import axis_aligned_expected_origins

    zero = axis_aligned_expected_origins((0, 0, 13.5, 15.5), 0.0, (-0.5, -0.5), 2.0, 4.0, 3.0, 5.0)
    assert scores[0]["table_count"] == len(zero)
    shifted_best = max(
        len(axis_aligned_expected_origins((0, 0, 13.5, 15.5), 0.0, (-0.5 + p, -0.5 + 5 * q / 3), 2.0, 4.0, 3.0, 5.0))
        for p in range(3)
        for q in range(3)
    )
    assert best == shifted_best * 4
    assert best > scores[0]["module_count"]  # this site rewards a phase shift


def test_c13_tie_break_prefers_phase_zero(rectangle):
    req = copy.deepcopy(rectangle)
    req["placement"]["mode"] = "phase_search_3x3"
    _, _, rr = run_layout(req)
    pl = rr.summary["placement"]
    best = max(s["module_count"] for s in pl["phase_candidates"])
    assert pl["phase_candidates"][0]["module_count"] == best
    assert pl["selected_phase_index"] == [0, 0]


def test_c13_deterministic_repeat():
    a = run_layout(phase_request())[2]
    b = run_layout(phase_request())[2]
    assert a.summary["placement"] == b.summary["placement"]
    assert a.payload_digest == b.payload_digest


# ---- C14 ------------------------------------------------------------------------------


def test_c14_equivalent_inputs_share_identity(rectangle):
    _, _, a = run_layout(rectangle)
    b_req = json.loads(json.dumps(rectangle))
    b_req["name"] = "renamed"  # labels are not numerical identity
    b_req["table"]["facing_azimuth_deg"] = 540  # equivalent azimuth
    b_req["module"]["width_m"] = 1  # int vs float
    b_req["perimeter_setback_m"] = 1
    _, _, b = run_layout(b_req)
    assert a.summary["input_digest"] == b.summary["input_digest"]
    assert a.result_id == b.result_id
    assert a.payload_digest == b.payload_digest


def test_c14_repeated_runs_identical(rectangle):
    digests = {run_layout(copy.deepcopy(rectangle))[2].payload_digest for _ in range(3)}
    assert len(digests) == 1


@pytest.mark.parametrize(
    "path,value",
    [
        (("perimeter_setback_m",), 1.5),
        (("table", "facing_azimuth_deg"), 181.0),
        (("placement", "anchor_xy_m"), [1.0, 1.5]),
        (("module", "power_wp"), 551.0),
        (("table", "lower_edge_height_m"), 0.9),
    ],
)
def test_c14_geometry_affecting_change_changes_identity(rectangle, path, value):
    _, _, a = run_layout(rectangle)
    r = copy.deepcopy(rectangle)
    target = r
    for p in path[:-1]:
        target = target[p]
    target[path[-1]] = value
    _, _, b = run_layout(r)
    assert a.summary["input_digest"] != b.summary["input_digest"]
    assert a.result_id != b.result_id
    assert a.payload_digest != b.payload_digest


def test_c14_payload_digest_excludes_wrappers(rectangle):
    _, _, a = run_layout(rectangle)
    assert "created_at" not in json.dumps(a.numeric_summary())
    assert "source_commit" not in json.dumps(a.numeric_summary())
