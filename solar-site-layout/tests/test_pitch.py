"""C05: limited row-pitch calculator."""

from __future__ import annotations

import math

import pytest

from conftest import load_fixture
from solar_layout.errors import DomainError
from solar_layout.pitch import calculate_row_pitch


def test_c05_3_4_5_fixture():
    req = load_fixture("pitch-3-4-5.request.json")
    exp = load_fixture("pitch-3-4-5.expected.json")
    out = calculate_row_pitch(req)
    tol = exp["tolerance_m"]
    assert out["projected_depth_m"] == pytest.approx(exp["projected_depth_m"], abs=tol)
    assert out["table_rise_m"] == pytest.approx(exp["table_rise_m"], abs=tol)
    assert out["shadow_clear_gap_m"] == pytest.approx(exp["shadow_clear_gap_m"], abs=tol)
    assert out["pitch_at_that_elevation_m"] == pytest.approx(exp["pitch_at_that_elevation_m"], abs=tol)
    assert out["recommended_pitch_m"] == pytest.approx(exp["recommended_pitch_m"], abs=tol)
    assert out["assumptions"] == exp["assumptions"]
    assert out["label"] == "2D row-spacing estimate at the specified solar elevation"
    # second path: the 3-4-5 triangle, D = sqrt(L^2 - H^2)
    assert math.sqrt(5.0**2 - out["table_rise_m"] ** 2) == pytest.approx(out["projected_depth_m"], abs=1e-9)


def base(**over):
    req = load_fixture("pitch-3-4-5.request.json")
    req.update(over)
    return req


def test_flat_tilt_only_clear_gap_remains():
    out = calculate_row_pitch(base(tilt_deg=0.0, minimum_clear_row_gap_m=0.7, solar_elevation_deg=5.0))
    assert out["table_rise_m"] == 0.0 and out["shadow_clear_gap_m"] == 0.0
    assert out["recommended_pitch_m"] == pytest.approx(5.0 + 0.7, abs=1e-12)
    assert out["governed_by"] == "minimum_clear_row_gap"
    # flat tables have no shadow even at a very low sun
    assert calculate_row_pitch(base(tilt_deg=0.0, solar_elevation_deg=0.01))["shadow_clear_gap_m"] == 0.0


def test_clearance_dominated_pitch():
    out = calculate_row_pitch(base(minimum_clear_row_gap_m=5.0))
    assert out["pitch_at_that_elevation_m"] == pytest.approx(7.0, abs=1e-9)
    assert out["recommended_pitch_m"] == pytest.approx(9.0, abs=1e-9)
    assert out["governed_by"] == "minimum_clear_row_gap"


def test_uses_total_rise_not_lower_edge_height():
    out = calculate_row_pitch(base(solar_elevation_deg=30.0))
    assert out["shadow_clear_gap_m"] == pytest.approx(3.0 / math.tan(math.radians(30.0)), abs=1e-9)


@pytest.mark.parametrize("alpha", [0.0, -5.0, 90.0001, 180.0])
def test_invalid_elevation(alpha):
    with pytest.raises(DomainError) as e:
        calculate_row_pitch(base(solar_elevation_deg=alpha))
    assert e.value.code == "INVALID_INPUT" and e.value.field == "/solar_elevation_deg"


def test_zenith_sun_has_no_shadow_gap():
    out = calculate_row_pitch(base(solar_elevation_deg=90.0))
    assert out["shadow_clear_gap_m"] == 0.0


@pytest.mark.parametrize("alpha", [1e-300, 1e-9, 0.5, 0.999])
def test_near_horizon_is_a_bounded_diagnostic(alpha):
    with pytest.raises(DomainError) as e:
        calculate_row_pitch(base(solar_elevation_deg=alpha))
    assert e.value.code == "UNSUPPORTED_INPUT"
    assert e.value.details["reason"] == "near_horizon"
    assert math.isfinite(e.value.details["shadow_clear_gap_at_minimum_m"])


def test_minimum_supported_elevation_is_finite():
    out = calculate_row_pitch(base(solar_elevation_deg=1.0))
    assert math.isfinite(out["recommended_pitch_m"]) and out["recommended_pitch_m"] < 200


@pytest.mark.parametrize("key,value", [("solar_azimuth_deg", 135.0), ("datetime", "2026-06-21T12:00:00+02:00"), ("time_window", ["09:00", "15:00"]), ("city", "Madrid")])
def test_azimuth_and_time_inputs_are_unsupported(key, value):
    with pytest.raises(DomainError) as e:
        calculate_row_pitch(base(**{key: value}))
    assert e.value.code == "UNSUPPORTED_INPUT" and e.value.field == f"/{key}"


def test_non_finite_and_unknown_fields():
    with pytest.raises(DomainError) as e:
        calculate_row_pitch(base(tilt_deg=float("nan")))
    assert e.value.code == "INVALID_INPUT"
    with pytest.raises(DomainError) as e:
        calculate_row_pitch(base(colour="red"))
    assert e.value.field == "/colour"
