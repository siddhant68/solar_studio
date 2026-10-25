"""Exact rational predicates on float coordinates.

Every float is an exact binary rational, so Fraction(x) is the coordinate exactly as
represented. These routines decide borderline distance and overlap questions without
rounding: they are only called for the few candidates whose float margin lies within
the declared distance band, so their cost is irrelevant to throughput.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Iterable, Sequence

Point = tuple[Fraction, Fraction]


def fr(p: Sequence[float]) -> Point:
    return Fraction(p[0]), Fraction(p[1])


def orient(a: Point, b: Point, c: Point) -> int:
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (v > 0) - (v < 0)


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Closed segments ab and cd share at least one point."""
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _on_segment(a, b, c):
        return True
    if o2 == 0 and _on_segment(a, b, d):
        return True
    if o3 == 0 and _on_segment(c, d, a):
        return True
    if o4 == 0 and _on_segment(c, d, b):
        return True
    return False


def point_segment_dist2(p: Point, a: Point, b: Point) -> Fraction:
    dx, dy = b[0] - a[0], b[1] - a[1]
    len2 = dx * dx + dy * dy
    if len2 == 0:
        ex, ey = p[0] - a[0], p[1] - a[1]
        return ex * ex + ey * ey
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2
    if t < 0:
        t = Fraction(0)
    elif t > 1:
        t = Fraction(1)
    cx, cy = a[0] + t * dx, a[1] + t * dy
    ex, ey = p[0] - cx, p[1] - cy
    return ex * ex + ey * ey


def segment_segment_dist2(a: Point, b: Point, c: Point, d: Point) -> Fraction:
    if segments_intersect(a, b, c, d):
        return Fraction(0)
    return min(
        point_segment_dist2(a, c, d),
        point_segment_dist2(b, c, d),
        point_segment_dist2(c, a, b),
        point_segment_dist2(d, a, b),
    )


def ring_segments(coords: Sequence[Sequence[float]]) -> list[tuple[Point, Point]]:
    pts = [fr(p) for p in coords]
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def min_dist2_quad_to_segments(quad: Sequence[Sequence[float]], segments: Iterable[tuple[Point, Point]]) -> Fraction:
    """Exact squared distance between the boundary of a closed quad and a set of segments."""
    q = [fr(p) for p in quad]
    edges = [(q[i], q[(i + 1) % 4]) for i in range(4)]
    best: Fraction | None = None
    for c, d in segments:
        for a, b in edges:
            d2 = segment_segment_dist2(a, b, c, d)
            if best is None or d2 < best:
                best = d2
                if best == 0:
                    return best
    assert best is not None
    return best


def distance_at_least(quad: Sequence[Sequence[float]], segments: list[tuple[Point, Point]], required: float) -> bool:
    """dist(boundary(quad), segments) >= required, decided exactly."""
    req = Fraction(required)
    return min_dist2_quad_to_segments(quad, segments) >= req * req


def segment_meets_open_convex(seg: tuple[Point, Point], poly: list[Point]) -> bool:
    """Does the closed segment meet the open interior of a convex polygon (CCW or CW)?

    Separating-axis test with strict inequalities on the polygon side: touching the
    polygon boundary does not count.
    """
    a, b = seg
    n = len(poly)
    sign = 0
    for i in range(n):
        s = orient(poly[i], poly[(i + 1) % n], poly[(i + 2) % n])
        if s != 0:
            sign = s
            break
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        # a point x is strictly inside the half-plane iff orient(p, q, x) == sign
        if orient(p, q, a) != sign and orient(p, q, b) != sign:
            # both endpoints on or outside this edge's line: segment cannot enter the open side
            return False
    # segment line as a separating axis: polygon strictly on one side (or touching) => no meeting
    sides = [orient(a, b, p) for p in poly]
    if all(s >= 0 for s in sides) or all(s <= 0 for s in sides):
        # The open interior lies on one closed side of the segment's line. It can still
        # straddle only if some vertex is strictly on each side.
        return False
    return True
