"""C09: setback and keepout distances against original geometry; tangent / just-inside /
just-outside cases; arc approximation cannot produce an unsafe placement."""

from __future__ import annotations

import copy
import math
from fractions import Fraction

import pytest
import shapely
from shapely.geometry import Polygon, box

from conftest import load_fixture, run_layout, shifted
from solar_layout import exact
from solar_layout.policy import ARC_QUAD_SEGMENTS


def one_table_request(anchor, setback=1.0, exclusions=(), site=(0, 0, 12, 14)):
    req = load_fixture("rectangle.request.json")
    x0, y0, x1, y1 = site
    req["boundary"]["coordinates"] = [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]
    req["perimeter_setback_m"] = setback
    req["exclusions"] = list(exclusions)
    req["placement"]["anchor_xy_m"] = list(anchor)
    # a lattice period larger than the site: only the anchor table can exist
    req["placement"]["table_gap_m"] = 100.0
    req["placement"]["row_pitch_m"] = 100.0
    return req


def kept(req):
    _, _, rr = run_layout(req)
    return [tuple(t["origin_xy_m"]) for t in rr.table_records()]


def test_setback_tangent_is_allowed_exactly():
    assert kept(one_table_request((1.0, 1.0))) == [(1.0, 1.0)]


@pytest.mark.parametrize("eps", [1e-6, 1e-9, 1e-12, 2**-40])
def test_setback_just_outside_is_rejected_just_inside_kept(eps):
    assert kept(one_table_request((1.0 - eps, 1.0))) == []
    assert kept(one_table_request((1.0 + eps, 1.0))) == [(1.0 + eps, 1.0)]


def test_borderline_cases_use_exact_arithmetic():
    _, comp, _ = run_layout(one_table_request((1.0 - 1e-12, 1.0)))
    assert comp.diagnostics["exact_borderline_checks"] >= 1


def keepout_exclusion(k):
    return {"id": "POST", "geometry": {"type": "Polygon", "coordinates": [[[6, 2], [7, 2], [7, 3], [6, 3], [6, 2]]]}, "keepout_m": k}


@pytest.mark.parametrize("dx,expect", [(0.0, True), (-1e-10, True), (1e-10, False), (1e-6, False), (2**-40, False)])
def test_keepout_tangent_and_neighbours(dx, expect):
    # table [x, x+2] x [1, 5]; exclusion [6,7] x [2,3]; keepout 1.5 -> right edge must be <= 4.5
    req = one_table_request((2.5 + dx, 1.0), exclusions=[keepout_exclusion(1.5)])
    assert (kept(req) != []) is expect


def test_keepout_corner_arc_is_a_true_circle_not_a_chord_polygon():
    """A table corner just inside the true keepout circle but outside GEOS's chord polygon.

    The exclusion square is [6,7]x[2,3]; its lower-left corner (6,2) has a keepout arc of radius k. Chord vertices sit every
    90/q degrees; between two of them the chord is k*cos(pi/(4q)) from the corner. A point
    at radius k*(1 - 1e-5) on the mid-angle lies inside the circle but outside the chords.
    """
    k = 2.0
    q = ARC_QUAD_SEGMENTS
    theta = math.radians(180 + 45 + 90 / q / 2)  # towards the lower-left, between two chord vertices
    r = k * (1 - 1e-5)
    cx, cy = 6 + r * math.cos(theta), 2 + r * math.sin(theta)
    # table extends from (cx-2, cy-4) to (cx, cy): its upper-right corner is the nearest point
    anchor = (cx - 2.0, cy - 4.0)
    req = one_table_request(anchor, setback=0.0, exclusions=[keepout_exclusion(k)], site=(-20, -20, 30, 30))
    # the trap: a buffer-polygon containment test would accept this table
    forbidden_chords = Polygon([(6, 2), (7, 2), (7, 3), (6, 3)]).buffer(k, quad_segs=q)
    fp = box(anchor[0], anchor[1], anchor[0] + 2, anchor[1] + 4)
    assert not forbidden_chords.intersects(fp)
    assert shapely.distance(fp, Polygon([(6, 2), (7, 2), (7, 3), (6, 3)])) < k
    assert kept(req) == []


def test_setback_reflex_vertex_arc_is_safe():
    """L-shaped site: the setback around the reflex vertex is a true circle."""
    s = 2.0
    q = ARC_QUAD_SEGMENTS
    req = load_fixture("rectangle.request.json")
    req["boundary"]["coordinates"] = [[[0, 0], [40, 0], [40, 20], [20, 20], [20, 40], [0, 40], [0, 0]]]
    req["perimeter_setback_m"] = s
    # Reflex vertex (20,20). Inside the L, below-left of it, the nearest boundary point is
    # the vertex itself, so the true setback boundary there is an arc of radius s.
    # Put the table's upper-right corner just inside that circle, between chord vertices.
    phi = math.radians(225 + 90 / q / 2)
    r = s * (1 - 1e-5)
    cx, cy = 20 + r * math.cos(phi), 20 + r * math.sin(phi)
    anchor = (cx - 2.0, cy - 4.0)
    req["placement"].update(anchor_xy_m=list(anchor), table_gap_m=100.0, row_pitch_m=100.0)
    site = Polygon([(0, 0), (40, 0), (40, 20), (20, 20), (20, 40), (0, 40)])
    fp = box(anchor[0], anchor[1], cx, cy)
    assert shapely.distance(fp, site.boundary) < s  # violates the true setback
    assert site.buffer(-s, quad_segs=q).covers(fp)  # ... yet a chord-polygon test accepts it
    _, _, rr = run_layout(req)
    assert rr.summary["quantities"]["table_count"] == 0


def test_buildable_area_bounds_bracket_an_analytic_area():
    """Square exclusion with keepout k inside a large site: forbidden area = a^2 + 4ak + pi k^2."""
    req = load_fixture("rectangle.request.json")
    req["boundary"]["coordinates"] = [[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]]
    req["perimeter_setback_m"] = 0.0
    req["exclusions"] = [{"id": "SQ", "geometry": {"type": "Polygon", "coordinates": [[[40, 40], [50, 40], [50, 50], [40, 50], [40, 40]]]}, "keepout_m": 3.0}]
    req["placement"]["anchor_xy_m"] = [1.0, 1.0]
    _, _, rr = run_layout(req)
    exact_area = 100 * 100 - (10 * 10 + 4 * 10 * 3 + math.pi * 9)
    lo, hi = rr.summary["quantities"]["buildable_area_bounds_m2"]
    assert lo <= exact_area <= hi
    assert hi - lo < 0.05
    assert rr.summary["quantities"]["buildable_area_m2"] == hi


def test_translated_tangency_still_exact():
    req = shifted(one_table_request((1.0, 1.0)), 7_000_000.0, 9_000_000.0)
    assert kept(req) == [(7_000_001.0, 9_000_001.0)]


# ---- exact kernel, hand-checked -------------------------------------------------------


def F(x, y):
    return (Fraction(x), Fraction(y))


def test_exact_point_segment_distance():
    assert exact.point_segment_dist2(F(0, 1), F(-1, 0), F(1, 0)) == 1
    assert exact.point_segment_dist2(F(3, 4), F(0, 0), F(0, 0)) == 25
    assert exact.point_segment_dist2(F(2, 1), F(-1, 0), F(1, 0)) == 2  # clamps to the endpoint


def test_exact_segment_intersection_cases():
    assert exact.segments_intersect(F(0, 0), F(2, 2), F(0, 2), F(2, 0))
    assert exact.segments_intersect(F(0, 0), F(1, 0), F(1, 0), F(2, 5))  # shared endpoint
    assert not exact.segments_intersect(F(0, 0), F(1, 0), F(0, 1), F(1, 1))
    assert exact.segments_intersect(F(0, 0), F(2, 0), F(1, 0), F(3, 0))  # collinear overlap


def test_exact_open_interior_meeting():
    sq = [F(0, 0), F(1, 0), F(1, 1), F(0, 1)]
    assert not exact.segment_meets_open_convex((F(0, 0), F(1, 0)), sq)  # along an edge
    assert not exact.segment_meets_open_convex((F(1, -1), F(1, 2)), sq)  # along the extended edge
    assert exact.segment_meets_open_convex((F(Fraction(1, 2), -1), F(Fraction(1, 2), 2)), sq)
    assert not exact.segment_meets_open_convex((F(1, 1), F(2, 2)), sq)  # touches a corner
    assert exact.segment_meets_open_convex((F(Fraction(1, 4), Fraction(1, 4)), F(Fraction(1, 3), Fraction(1, 3))), sq)


def test_distance_at_least_is_exact_for_float_representation():
    quad = [(1.0, 1.0), (3.0, 1.0), (3.0, 5.0), (1.0, 5.0)]
    segs = exact.ring_segments([(0.0, 0.0), (12.0, 0.0)])
    assert exact.distance_at_least(quad, segs, 1.0)
    assert not exact.distance_at_least(quad, segs, 1.0 + 2**-52)
