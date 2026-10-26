"""C01 (typed field errors) and C12 (envelope and limits before unbounded work)."""

from __future__ import annotations

import copy
import sqlite3
import time

import pytest

from conftest import load_fixture, run_layout
from solar_layout.errors import DomainError
from solar_layout.jsonio import loads_strict
from solar_layout.validation import validate_layout_request


def err(req) -> DomainError:
    with pytest.raises(DomainError) as e:
        validate_layout_request(req)
    return e.value


def codes(e: DomainError):
    return {(x.code, x.field) for x in e.errors} or {(e.code, e.field)}


@pytest.fixture
def req():
    return load_fixture("rectangle.request.json")


def test_fixtures_are_valid_without_migration():
    for name in ("rectangle", "obstacle", "multipolygon", "concave-notch", "hole"):
        validate_layout_request(load_fixture(f"{name}.request.json"))


def test_missing_units_and_frame(req):
    r = copy.deepcopy(req)
    del r["frame"]["units"]
    e = err(r)
    assert e.code == "INVALID_INPUT" and ("INVALID_INPUT", "/frame") in codes(e)
    assert "units" in e.message
    r = copy.deepcopy(req)
    del r["frame"]
    assert err(r).code == "INVALID_INPUT"


@pytest.mark.parametrize(
    "mutate,field",
    [
        (lambda r: r["frame"].__setitem__("units", "deg"), "/frame/units"),
        (lambda r: r["frame"].__setitem__("units", "ft"), "/frame/units"),
        (lambda r: r["frame"].__setitem__("kind", "geographic"), "/frame/kind"),
        (lambda r: r["frame"].__setitem__("id", "EPSG:4326"), "/frame/id"),
        (lambda r: r["frame"].__setitem__("axes", {"x": "north", "y": "east"}), "/frame/axes"),
    ],
)
def test_unsupported_frames_are_typed(req, mutate, field):
    r = copy.deepcopy(req)
    mutate(r)
    e = err(r)
    assert e.code == "UNSUPPORTED_FRAME"
    assert ("UNSUPPORTED_FRAME", field) in codes(e)


def test_projected_frame_requires_and_retains_crs(req):
    r = copy.deepcopy(req)
    r["frame"]["kind"] = "projected_cartesian"
    e = err(r)
    assert ("INVALID_INPUT", "/frame/crs") in codes(e)
    r["frame"]["crs"] = "EPSG:32633"
    val = validate_layout_request(r)
    assert val.normalized["frame"]["crs"] == "EPSG:32633"


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_non_finite_json_is_rejected(token):
    text = '{"a": %s}' % token
    with pytest.raises(DomainError) as e:
        loads_strict(text)
    assert e.value.code == "INVALID_INPUT"
    assert e.value.details["reason"] == "non_finite_number"


def test_non_finite_python_values_are_rejected(req):
    r = copy.deepcopy(req)
    r["boundary"]["coordinates"][0][1][0] = float("nan")
    e = err(r)
    assert ("INVALID_INPUT", "/boundary/coordinates/0/1/0") in codes(e)
    r = copy.deepcopy(req)
    r["placement"]["row_pitch_m"] = float("inf")
    assert ("INVALID_INPUT", "/placement/row_pitch_m") in codes(err(r))


def test_degenerate_and_open_rings(req):
    r = copy.deepcopy(req)
    r["boundary"]["coordinates"] = [[[0, 0], [12, 0], [12, 14], [0, 14]]]  # not closed
    e = err(r)
    assert e.code == "INVALID_GEOMETRY" and e.details["reason"] == "ring_not_closed"
    assert e.field == "/boundary/coordinates/0"
    r["boundary"]["coordinates"] = [[[0, 0], [5, 0], [10, 0], [0, 0]]]  # zero area
    e = err(r)
    assert e.code == "INVALID_GEOMETRY"
    r["boundary"]["coordinates"] = [[[0, 0], [1, 1], [0, 0]]]
    assert err(r).details["reason"] == "too_few_positions"


def test_self_crossing_ring_is_rejected_not_repaired(req):
    r = copy.deepcopy(req)
    r["boundary"]["coordinates"] = [[[0, 0], [12, 14], [12, 0], [0, 14], [0, 0]]]
    e = err(r)
    assert e.code == "INVALID_GEOMETRY" and "Self-intersection" in e.message
    assert e.field == "/boundary/coordinates"


@pytest.mark.parametrize(
    "holes",
    [
        [[[20, 20], [21, 20], [21, 21], [20, 21], [20, 20]]],  # hole outside shell
        [[[-1, 5], [5, 5], [5, 6], [-1, 6], [-1, 5]]],  # hole crossing shell
        [[[2, 2], [8, 2], [8, 8], [2, 8], [2, 2]], [[3, 3], [4, 3], [4, 4], [3, 4], [3, 3]]],  # nested holes
    ],
)
def test_bad_holes_are_rejected(req, holes):
    r = copy.deepcopy(req)
    r["boundary"]["coordinates"] = r["boundary"]["coordinates"] + holes
    assert err(r).code == "INVALID_GEOMETRY"


def test_overlapping_multipolygon_components_rejected(req):
    r = copy.deepcopy(req)
    sq = [[0, 0], [12, 0], [12, 14], [0, 14], [0, 0]]
    sq2 = [[6, 0], [18, 0], [18, 14], [6, 14], [6, 0]]
    r["boundary"] = {"type": "MultiPolygon", "coordinates": [[sq], [sq2]]}
    assert err(r).code == "INVALID_GEOMETRY"


def test_z_coordinates_are_unsupported(req):
    r = copy.deepcopy(req)
    r["boundary"]["coordinates"][0] = [[x, y, 100.0] for x, y in r["boundary"]["coordinates"][0]]
    e = err(r)
    assert e.code == "UNSUPPORTED_INPUT" and e.field == "/boundary/coordinates/0/0"
    assert e.details["reason"] == "z_coordinate_unsupported"


def test_invalid_exclusion_and_duplicate_ids(req):
    r = load_fixture("obstacle.request.json")
    r["exclusions"].append(copy.deepcopy(r["exclusions"][0]))
    e = err(r)
    assert ("INVALID_INPUT", "/exclusions/1/id") in codes(e)
    r = load_fixture("obstacle.request.json")
    r["exclusions"][0]["geometry"]["coordinates"] = [[[4, 1], [6, 5], [6, 1], [4, 5], [4, 1]]]
    e = err(r)
    assert e.code == "INVALID_GEOMETRY" and e.field.startswith("/exclusions/0/geometry")


@pytest.mark.parametrize(
    "path,value",
    [
        (("table", "tilt_deg"), 81),
        (("table", "tilt_deg"), -1),
        (("table", "rows"), 0),
        (("table", "rows"), 1.5),
        (("module", "orientation"), "diagonal"),
        (("placement", "mode"), "global_optimum"),
        (("module", "width_m"), 0),
        (("perimeter_setback_m",), -1),
    ],
)
def test_schema_ranges_are_typed_field_errors(req, path, value):
    r = copy.deepcopy(req)
    target = r
    for p in path[:-1]:
        target = target[p]
    target[path[-1]] = value
    e = err(r)
    assert e.code == "INVALID_INPUT"
    assert e.field == "/" + "/".join(path)


def test_width_must_be_short_side(req):
    r = copy.deepcopy(req)
    r["module"]["width_m"], r["module"]["length_m"] = 2.0, 1.0
    assert err(r).field == "/module/width_m"


def test_invalid_pitch_is_rejected_not_adjusted(req):
    r = copy.deepcopy(req)
    r["placement"]["row_pitch_m"] = 4.5  # D=4, min gap 1 -> needs 5
    e = err(r)
    assert e.code == "INVALID_PITCH" and e.details["required_pitch_m"] == 5.0
    r["placement"]["row_pitch_m"] = 3.9  # rows would overlap physically
    e = err(r)
    assert e.code == "INVALID_PITCH" and "overlap" in e.message
    r["placement"]["row_pitch_m"] = 5.0
    validate_layout_request(r)


# ---- C12 envelope and limits ---------------------------------------------------------


def test_coordinate_magnitude_limit(req):
    from conftest import shifted

    r = shifted(req, 9_999_990.0, 0.0)  # x up to 10,000,002
    e = err(r)
    assert e.code == "RESOURCE_LIMIT" and e.details["limit"] == "max_abs_coordinate_m"
    validate_layout_request(shifted(req, 9_999_980.0, -9_999_980.0))


def test_site_diagonal_limit(req):
    r = copy.deepcopy(req)
    r["boundary"]["coordinates"] = [[[0, 0], [15000, 0], [15000, 15000], [0, 15000], [0, 0]]]
    e = err(r)
    assert e.code == "RESOURCE_LIMIT" and e.details["limit"] == "max_site_diagonal_m"


def test_module_dimension_envelope(req):
    r = copy.deepcopy(req)
    r["module"]["width_m"] = 0.04
    e = err(r)
    assert e.code == "RESOURCE_LIMIT" and e.details["limit"] == "min_module_dimension_m"


def test_anchor_must_be_near_site(req):
    r = copy.deepcopy(req)
    r["placement"]["anchor_xy_m"] = [50_000.0, 0.0]
    assert err(r).details["limit"] == "max_anchor_distance_from_site_bbox_m"


def test_candidate_limit_rejected_before_work(req):
    r = copy.deepcopy(req)
    r["boundary"]["coordinates"] = [[[0, 0], [14000, 0], [14000, 14000], [0, 14000], [0, 0]]]
    r["module"].update(width_m=0.05, length_m=0.05)
    r["table"].update(rows=1, columns=1)
    r["placement"].update(table_gap_m=0.0, row_pitch_m=0.05, minimum_clear_row_gap_m=0.0)
    from solar_layout.layout import compute_layout

    val = validate_layout_request(r)
    t = time.monotonic()
    with pytest.raises(DomainError) as e:
        compute_layout(val)
    assert e.value.code == "RESOURCE_LIMIT"
    assert e.value.details["limit"] in ("max_candidates_total", "max_candidates_per_phase")
    assert time.monotonic() - t < 2.0


def test_module_output_limit(req):
    r = copy.deepcopy(req)
    r["boundary"]["coordinates"] = [[[0, 0], [400, 0], [400, 400], [0, 400], [0, 0]]]
    r["module"].update(width_m=0.5, length_m=0.5)
    r["table"].update(rows=4, columns=10)
    r["placement"].update(table_gap_m=0.0, row_pitch_m=2.0, minimum_clear_row_gap_m=0.0)
    with pytest.raises(DomainError) as e:
        run_layout(r)
    assert e.value.code == "RESOURCE_LIMIT" and e.value.details["limit"] == "max_modules"


def test_timeout_policy_is_finite_and_typed(req):
    with pytest.raises(DomainError) as e:
        run_layout(req, timeout_s=0.0)
    assert e.value.code == "RESOURCE_LIMIT" and e.value.details["limit"] == "generation_timeout_s"


def test_timeout_covers_records_and_verification_not_only_compute(tmp_path, monkeypatch):
    """Found when re-running D03 after the review repair: the time limit was checked only
    inside the layout engine, so a fast compute stage let a timed-out generation run its
    record construction and verification and be stored. The service now checks the same
    deadline after those stages, before persisting."""
    import solar_layout.service as service_mod
    from solar_layout.service import SolarService

    svc = SolarService(tmp_path / "d")
    real_verify = service_mod.verify_records

    def slow_verify(*a, **k):
        time.sleep(0.3)
        return real_verify(*a, **k)

    monkeypatch.setattr(service_mod, "verify_records", slow_verify)
    with pytest.raises(DomainError) as e:
        svc.generate_layout(request=load_fixture("rectangle.request.json"), timeout_s=0.2)
    assert e.value.code == "RESOURCE_LIMIT" and e.value.details["stage"] == "independent verification"
    with sqlite3.connect(svc.store.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 0
    monkeypatch.setattr(service_mod, "verify_records", real_verify)
    assert svc.generate_layout(request=load_fixture("rectangle.request.json"), timeout_s=60)["verification"]["ok"]
