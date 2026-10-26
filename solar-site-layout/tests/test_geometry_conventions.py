"""C04 (portrait/landscape, gaps, tilt dimensions) and C06 (azimuth axes, corners, heights)."""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from conftest import load_fixture, run_layout
from solar_layout.geometry import normalize_azimuth, table_axes

TILT_345 = math.degrees(math.atan2(3.0, 4.0))  # 36.86989764584402


def big_site(req, size=200.0):
    r = copy.deepcopy(req)
    r["boundary"]["coordinates"] = [[[0, 0], [size, 0], [size, size], [0, size], [0, 0]]]
    r["perimeter_setback_m"] = 0.0
    r["placement"]["anchor_xy_m"] = [size / 2, size / 2]
    return r


def test_c04_landscape_gaps_and_tilt_hand_calculation():
    req = big_site(load_fixture("rectangle.request.json"))
    req["module"].update(width_m=1.0, length_m=2.0, orientation="landscape")
    req["table"].update(rows=2, columns=3, module_gap_x_m=0.1, module_gap_y_m=0.05, tilt_deg=TILT_345)
    req["placement"].update(row_pitch_m=4.0, minimum_clear_row_gap_m=0.0, table_gap_m=0.5)
    _, _, rr = run_layout(req)
    d = rr.summary["dimensions"]
    # hand calculation: landscape swaps -> w=2 across, l=1 up the slope
    assert (d["module_w_across_m"], d["module_l_upslope_m"]) == (2.0, 1.0)
    assert d["table_width_W_m"] == pytest.approx(3 * 2 + 2 * 0.1, abs=1e-12)  # 6.2
    assert d["table_slope_length_L_m"] == pytest.approx(2 * 1 + 0.05, abs=1e-12)  # 2.05
    assert d["table_projected_depth_D_m"] == pytest.approx(2.05 * 4 / 5, abs=1e-12)  # 1.64
    assert d["table_rise_H_m"] == pytest.approx(2.05 * 3 / 5, abs=1e-12)  # 1.23
    q = rr.summary["quantities"]
    t = q["table_count"]
    assert t > 0
    # module area (6 modules x 2 m2 per table) differs from the table envelope (gaps included)
    assert q["physical_module_area_m2"] == pytest.approx(t * 12.0, abs=1e-9)
    assert q["projected_module_area_m2"] == pytest.approx(t * 12.0 * 0.8, abs=1e-9)
    assert q["table_footprint_area_m2"] == pytest.approx(t * 6.2 * 1.64, abs=1e-9)
    assert q["table_footprint_area_m2"] > q["projected_module_area_m2"]


def test_c04_portrait_vs_landscape_swap_and_gap_positions():
    base = big_site(load_fixture("rectangle.request.json"))
    base["table"].update(rows=1, columns=2, module_gap_x_m=0.25)
    base["placement"].update(row_pitch_m=4.0, minimum_clear_row_gap_m=0.0)
    _, _, rr = run_layout(base)
    t0 = next(rr.table_records())
    mods = [m for m in rr.module_records() if m["table_id"] == t0["table_id"]]
    ox, oy = t0["origin_xy_m"]
    # south facing: u = East. Column 0 spans [0,1], gap 0.25, column 1 spans [1.25, 2.25]
    xs = sorted({round(c[0] - ox, 12) for m in mods for c in m["corners_xyz_m"]})
    assert xs == [0.0, 1.0, 1.25, 2.25]
    assert rr.summary["dimensions"]["table_width_W_m"] == 2.25
    land = copy.deepcopy(base)
    land["module"]["orientation"] = "landscape"
    land["placement"]["row_pitch_m"] = 2.0
    _, _, rr2 = run_layout(land)
    assert rr2.summary["dimensions"]["table_width_W_m"] == 2 * 2.0 + 0.25
    assert rr2.summary["dimensions"]["table_slope_length_L_m"] == 1.0


def test_c04_3_4_5_module_corner_heights_second_path():
    """Second calculation path: 5 m slope at tilt atan(3/4) rises 3 m over 4 m horizontal."""
    req = big_site(load_fixture("rectangle.request.json"))
    req["module"].update(width_m=2.0, length_m=5.0)
    req["table"].update(rows=1, columns=1, tilt_deg=TILT_345, lower_edge_height_m=0.8)
    req["placement"].update(row_pitch_m=7.0, minimum_clear_row_gap_m=0.5, table_gap_m=1.0)
    _, _, rr = run_layout(req)
    m = next(rr.module_records())
    c = np.array(m["corners_xyz_m"])
    # lower edge corners at 0.8, upper edge corners at 0.8 + 3 = 3.8
    assert c[0, 2] == pytest.approx(0.8, abs=1e-9) and c[1, 2] == pytest.approx(0.8, abs=1e-9)
    assert c[2, 2] == pytest.approx(3.8, abs=1e-9) and c[3, 2] == pytest.approx(3.8, abs=1e-9)
    # upper edge is 4 m north of the lower edge in plan (south-facing)
    assert c[3, 1] - c[0, 1] == pytest.approx(4.0, abs=1e-9)
    assert c[3, 0] - c[0, 0] == pytest.approx(0.0, abs=1e-12)
    # slope length recovered from 3D corners
    assert np.linalg.norm(c[3] - c[0]) == pytest.approx(5.0, abs=1e-9)
    d = rr.summary["dimensions"]
    assert d["upper_edge_height_m"] == pytest.approx(3.8, abs=1e-9)


EXACT_AXES = {
    0: ((-1.0, 0.0), (0.0, -1.0)),  # north-facing: rises towards south
    90: ((0.0, 1.0), (-1.0, 0.0)),  # east-facing: rises towards west
    180: ((1.0, 0.0), (0.0, 1.0)),  # south-facing: rises towards north
    270: ((0.0, -1.0), (1.0, 0.0)),  # west-facing: rises towards east
}


@pytest.mark.parametrize("az", [0, 90, 180, 270])
def test_c06_cardinal_axes_are_exact(az):
    u, v = table_axes(az)
    assert (u, v) == EXACT_AXES[az]


def bearing_deg(vec) -> float:
    """Compass bearing (clockwise from north) of an East/North vector, via atan2."""
    return math.degrees(math.atan2(vec[0], vec[1])) % 360.0


@pytest.mark.parametrize("az", [0, 17, 37, 73, 90, 180, 270])
def test_c06_facing_direction_and_rise(az):
    u, v = table_axes(az)
    # the panel faces opposite to the uphill axis: bearing of -v must be A
    assert bearing_deg((-v[0], -v[1])) == pytest.approx(az % 360, abs=1e-9) or (az == 0 and bearing_deg((-v[0], -v[1])) == pytest.approx(360.0, abs=1e-9))
    assert u[0] * v[1] - u[1] * v[0] == pytest.approx(1.0, abs=1e-15)  # CCW corner order
    assert u[0] * v[0] + u[1] * v[1] == pytest.approx(0.0, abs=1e-15)
    # table width axis is 90 deg anticlockwise from the facing direction
    assert bearing_deg(u) == pytest.approx((az - 90) % 360, abs=1e-9)


@pytest.mark.parametrize("az", [0, 17, 37, 73, 90, 180, 270])
def test_c06_upper_edge_is_away_from_facing_side(az):
    req = big_site(load_fixture("rectangle.request.json"))
    req["table"].update(rows=1, columns=1, tilt_deg=TILT_345, facing_azimuth_deg=az, lower_edge_height_m=0.5)
    req["module"].update(width_m=2.0, length_m=5.0)
    req["placement"].update(row_pitch_m=8.0, minimum_clear_row_gap_m=0.0, table_gap_m=1.0)
    _, _, rr = run_layout(req)
    m = next(rr.module_records())
    c = np.array(m["corners_xyz_m"])
    facing = np.array([math.sin(math.radians(az)), math.cos(math.radians(az))])
    lower_mid = (c[0, :2] + c[1, :2]) / 2
    upper_mid = (c[2, :2] + c[3, :2]) / 2
    # upper edge is 4 m behind the lower edge, opposite to the facing direction
    assert float((upper_mid - lower_mid) @ facing) == pytest.approx(-4.0, abs=1e-9)
    assert c[2, 2] - c[1, 2] == pytest.approx(3.0, abs=1e-9)
    # lower edge runs along u; width 2 m
    assert np.linalg.norm(c[1, :2] - c[0, :2]) == pytest.approx(2.0, abs=1e-12)
    # an azimuth reversed by 180 deg would put the upper edge in front: guard explicitly
    assert float((upper_mid - lower_mid) @ -facing) > 0


@pytest.mark.parametrize("a,expected", [(540, 180.0), (-90, 270.0), (360, 0.0), (-0.0, 0.0), (-1e-20, 0.0), (725.5, 5.5)])
def test_azimuth_normalization(a, expected):
    assert normalize_azimuth(a) == expected
    assert table_axes(a) == table_axes(expected)
