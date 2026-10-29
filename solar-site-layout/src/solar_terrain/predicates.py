"""Exact geometric predicates of terrain-policy/1 for surface validation and the placement engine.

The independent verifier (verify.py) has its own exact arithmetic and does not import this
module (import-boundary test).

orient(a, b, c) = (ax - cx)(by - cy) - (ay - cy)(bx - cx): positive when a, b, c turn
counter-clockwise. Its sign is decided in three stages, vectorized with numpy:

1. Filter (Shewchuk's orient2d stage A) on the original doubles. The signs of the two
   products are exact (a difference of doubles is zero only if they are equal, and rounding
   keeps signs), so opposite or zero product signs decide immediately. Otherwise the double
   result is certain when |det| > (3 + 16e)e (|left| + |right|), e = 2^-53, and the
   products are well clear of underflow.
2. Exact expansion: the six coordinate products are formed exactly with Dekker's
   two-product, summed exactly with Shewchuk's grow-expansion, and the sign read from the
   most significant nonzero component.
3. Rational arithmetic (fractions.Fraction) for entries with tiny nonzero coordinates, where
   the exact products could underflow.

Rational points (footprint centroid, support positions) are tested with Fraction.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Iterable

import numpy as np

EPS = 2.0**-53
CCW_ERRBOUND_A = (3.0 + 16.0 * EPS) * EPS
_SPLITTER = 134217729.0  # 2**27 + 1
_MIN_DETSUM = 1e-280  # below this the filter does not trust the products
_TINY = 2.0**-400  # nonzero coordinates below this go straight to Fraction


class ExactStats:
    """Counts of decisions that needed the exact stages (reported in diagnostics)."""

    def __init__(self) -> None:
        self.orientations = 0
        self.expansion = 0
        self.fraction = 0
        self.rational_points = 0
        self.slope_exact = 0
        self.support_band_exact = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "orientations_evaluated": self.orientations,
            "orientations_exact_expansion": self.expansion,
            "orientations_exact_rational": self.fraction,
            "rational_point_tests": self.rational_points,
            "slope_decisions_exact": self.slope_exact,
            "support_limit_exact_recomputations": self.support_band_exact,
        }


# ---- error-free transformations (vectorized) ---------------------------------------------


def _two_sum(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    s = a + b
    bv = s - a
    av = s - bv
    return s, (a - av) + (b - bv)


def _split(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    c = _SPLITTER * a
    hi = c - (c - a)
    return hi, a - hi


def _two_product(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = a * b
    ah, al = _split(a)
    bh, bl = _split(b)
    err = al * bl - (((p - ah * bh) - al * bh) - ah * bl)
    return p, err


def _expansion_sign(terms: Iterable[np.ndarray]) -> np.ndarray:
    """Exact sign of a sum of doubles (Shewchuk grow-expansion, zero components kept)."""
    expansion: list[np.ndarray] = []
    for t in terms:
        q = t
        grown = []
        for comp in expansion:
            q, low = _two_sum(q, comp)
            grown.append(low)
        grown.append(q)
        expansion = grown
    sign = np.zeros(expansion[0].shape, dtype=np.int8)
    for comp in reversed(expansion):
        sign = np.where(sign == 0, np.sign(comp).astype(np.int8), sign)
    return sign


def _orient_expansion(ax, ay, bx, by, cx, cy) -> np.ndarray:
    # orient = ax*by - ax*cy - by*cx - ay*bx + ay*cx + bx*cy, every product exact
    terms = []
    for p, q, neg in ((ax, by, False), (ax, cy, True), (by, cx, True), (ay, bx, True), (ay, cx, False), (bx, cy, False)):
        hi, lo = _two_product(p, q)
        if neg:
            hi, lo = -hi, -lo
        terms.append(lo)
        terms.append(hi)
    return _expansion_sign(terms)


def orient_fraction(a, b, c) -> int:
    """Exact orientation sign of three points given as (Fraction|float, Fraction|float)."""
    ax, ay = Fraction(a[0]), Fraction(a[1])
    bx, by = Fraction(b[0]), Fraction(b[1])
    cx, cy = Fraction(c[0]), Fraction(c[1])
    det = (ax - cx) * (by - cy) - (ay - cy) * (bx - cx)
    return (det > 0) - (det < 0)


def orient_sign(ax, ay, bx, by, cx, cy, stats: ExactStats | None = None) -> np.ndarray:
    """Exact sign (-1, 0, 1) of orient(a, b, c) for broadcastable arrays of doubles."""
    ax, ay, bx, by, cx, cy = np.broadcast_arrays(*(np.asarray(v, dtype=np.float64) for v in (ax, ay, bx, by, cx, cy)))
    dl1 = ax - cx
    dl2 = by - cy
    dr1 = ay - cy
    dr2 = bx - cx
    sl = (np.sign(dl1) * np.sign(dl2)).astype(np.int8)
    sr = (np.sign(dr1) * np.sign(dr2)).astype(np.int8)
    out = np.where(sl != sr, np.where(sl != 0, sl, -sr), 0).astype(np.int8)
    same = (sl == sr) & (sl != 0)
    if stats is not None:
        stats.orientations += int(out.size)
    if not same.any():
        return out
    detl = dl1 * dl2
    detr = dr1 * dr2
    det = detl - detr
    detsum = np.abs(detl) + np.abs(detr)
    certain = same & (detsum >= _MIN_DETSUM) & (np.abs(det) > CCW_ERRBOUND_A * detsum)
    out[certain] = np.sign(det[certain]).astype(np.int8)
    unsure = same & ~certain
    if not unsure.any():
        return out
    idx = np.nonzero(unsure)
    pts = [v[idx] for v in (ax, ay, bx, by, cx, cy)]
    stack = np.abs(np.stack(pts))
    tiny = ((stack > 0) & (stack < _TINY)).any(axis=0)
    signs = np.empty(len(pts[0]), dtype=np.int8)
    ok = ~tiny
    if ok.any():
        signs[ok] = _orient_expansion(*(p[ok] for p in pts))
        if stats is not None:
            stats.expansion += int(ok.sum())
    for k in np.nonzero(tiny)[0]:
        signs[k] = orient_fraction((pts[0][k], pts[1][k]), (pts[2][k], pts[3][k]), (pts[4][k], pts[5][k]))
        if stats is not None:
            stats.fraction += 1
    out[idx] = signs
    return out


# ---- composite predicates ----------------------------------------------------------------


def point_in_closed_convex(poly: np.ndarray, px: np.ndarray, py: np.ndarray, stats: ExactStats | None = None) -> np.ndarray:
    """Points (px, py) in the closed convex polygon `poly` ((k, 2), counter-clockwise)."""
    inside = np.ones(np.shape(px), dtype=bool)
    k = len(poly)
    for i in range(k):
        a, b = poly[i], poly[(i + 1) % k]
        inside &= orient_sign(a[0], a[1], b[0], b[1], px, py, stats) >= 0
    return inside


def triangles_meet_open_convex(tri_xy: np.ndarray, poly: np.ndarray, stats: ExactStats | None = None) -> np.ndarray:
    """Whether each triangle's open interior meets the open convex polygon (separating-edge test).

    tri_xy: (n, 3, 2) counter-clockwise triangles; poly: (k, 2) counter-clockwise. Two open
    convex polygons are disjoint iff the supporting line of an edge of one of them has the
    other polygon in its closed outer half-plane.
    """
    n = tri_xy.shape[0]
    separated = np.zeros(n, dtype=bool)
    k = len(poly)
    for i in range(k):
        a, b = poly[i], poly[(i + 1) % k]
        s = orient_sign(a[0], a[1], b[0], b[1], tri_xy[:, :, 0], tri_xy[:, :, 1], stats)
        separated |= (s <= 0).all(axis=1)
    for e in range(3):
        a = tri_xy[:, e, :]
        b = tri_xy[:, (e + 1) % 3, :]
        s = orient_sign(a[:, None, 0], a[:, None, 1], b[:, None, 0], b[:, None, 1], poly[None, :, 0], poly[None, :, 1], stats)
        separated |= (s <= 0).all(axis=1)
    return ~separated


def segments_meet_open_convex(seg: np.ndarray, poly: np.ndarray, stats: ExactStats | None = None) -> np.ndarray:
    """Whether each closed segment ((n, 2, 2)) meets the open convex polygon ((k, 2), CCW).

    Disjoint iff both endpoints lie in the closed outer half-plane of one polygon edge, or
    every polygon vertex lies on one closed side of the segment's line.
    """
    n = seg.shape[0]
    if n == 0:
        return np.zeros(0, dtype=bool)
    separated = np.zeros(n, dtype=bool)
    k = len(poly)
    for i in range(k):
        a, b = poly[i], poly[(i + 1) % k]
        s = orient_sign(a[0], a[1], b[0], b[1], seg[:, :, 0], seg[:, :, 1], stats)
        separated |= (s <= 0).all(axis=1)
    p, q = seg[:, 0, :], seg[:, 1, :]
    s = orient_sign(p[:, None, 0], p[:, None, 1], q[:, None, 0], q[:, None, 1], poly[None, :, 0], poly[None, :, 1], stats)
    separated |= (s >= 0).all(axis=1) | (s <= 0).all(axis=1)
    return ~separated


def proper_crossings(ea: np.ndarray, eb: np.ndarray, pa: np.ndarray, pb: np.ndarray, stats: ExactStats | None = None) -> np.ndarray:
    """Whether segments (ea, eb) and (pa, pb) cross at a point interior to both (exact)."""
    s1 = orient_sign(ea[..., 0], ea[..., 1], eb[..., 0], eb[..., 1], pa[..., 0], pa[..., 1], stats)
    s2 = orient_sign(ea[..., 0], ea[..., 1], eb[..., 0], eb[..., 1], pb[..., 0], pb[..., 1], stats)
    s3 = orient_sign(pa[..., 0], pa[..., 1], pb[..., 0], pb[..., 1], ea[..., 0], ea[..., 1], stats)
    s4 = orient_sign(pa[..., 0], pa[..., 1], pb[..., 0], pb[..., 1], eb[..., 0], eb[..., 1], stats)
    return (s1.astype(np.int16) * s2 < 0) & (s3.astype(np.int16) * s4 < 0)


def rational_point_in_closed_triangle(tri: np.ndarray, p: tuple[Fraction, Fraction], stats: ExactStats | None = None) -> bool:
    """Exact closed containment of a rational point in a counter-clockwise triangle ((3, 2) doubles)."""
    if stats is not None:
        stats.rational_points += 1
    for e in range(3):
        a, b = tri[e], tri[(e + 1) % 3]
        if orient_fraction((float(a[0]), float(a[1])), (float(b[0]), float(b[1])), p) < 0:
            return False
    return True


def locate_rational(
    tri_xy: np.ndarray, candidates: np.ndarray, p: tuple[Fraction, Fraction], p_approx: tuple[float, float], stats: ExactStats | None = None
) -> int:
    """Lowest index among `candidates` (ascending global triangle indices, with their
    (n, 3, 2) coordinates `tri_xy`) whose closed triangle contains the rational point p.

    A double pre-test discards triangles the point is clearly outside of: more than 1e-6 m
    beyond an edge line, far above any rounding of p_approx or of the double orientation.
    Returns -1 if no candidate contains p.
    """
    if len(candidates) == 0:
        return -1
    px, py = p_approx
    a = tri_xy
    b = np.roll(tri_xy, -1, axis=1)
    ex = b[:, :, 0] - a[:, :, 0]
    ey = b[:, :, 1] - a[:, :, 1]
    o = ex * (py - a[:, :, 1]) - ey * (px - a[:, :, 0])
    length = np.hypot(ex, ey)
    clearly_out = (o < -1e-6 * length).any(axis=1)
    for k in np.nonzero(~clearly_out)[0]:
        if rational_point_in_closed_triangle(tri_xy[k], p, stats):
            return int(candidates[k])
    return -1


def exact_area2_exceeds(tri_xy: np.ndarray, threshold2: Fraction, stats: ExactStats | None = None) -> np.ndarray:
    """Exact test orient(p0, p1, p2) > threshold2 for (n, 3, 2) triangles (twice the signed area)."""
    x0, y0 = tri_xy[:, 0, 0], tri_xy[:, 0, 1]
    x1, y1 = tri_xy[:, 1, 0], tri_xy[:, 1, 1]
    x2, y2 = tri_xy[:, 2, 0], tri_xy[:, 2, 1]
    detl = (x0 - x2) * (y1 - y2)
    detr = (y0 - y2) * (x1 - x2)
    det = detl - detr
    bound = CCW_ERRBOUND_A * (np.abs(detl) + np.abs(detr))
    t = float(threshold2)
    margin = bound + 1e-22 + 4 * EPS * np.abs(det)
    out = det - t > margin
    unsure = ~out & ~(det - t < -margin)
    for k in np.nonzero(unsure)[0]:
        fx = [Fraction(float(v)) for v in (x0[k], y0[k], x1[k], y1[k], x2[k], y2[k])]
        d = (fx[0] - fx[4]) * (fx[3] - fx[5]) - (fx[1] - fx[5]) * (fx[2] - fx[4])
        out[k] = d > threshold2
        if stats is not None:
            stats.fraction += 1
    return out


def gradient_exceeds(tri_xyz: np.ndarray, t: float, stats: ExactStats | None = None) -> np.ndarray:
    """Exact test g^2 > t^2 for (n, 3, 3) counter-clockwise triangles of positive area.

    g^2 = (Nx^2 + Ny^2) / A2^2 with Nx = dz1 dy2 - dz2 dy1, Ny = dx1 dz2 - dx2 dz1 and
    A2 = dx1 dy2 - dx2 dy1 (differences from vertex 0). A generous a-priori error bound on
    the double values decides clear cases; the rest is decided in rationals.
    """
    p0 = tri_xyz[:, 0, :]
    d1 = tri_xyz[:, 1, :] - p0
    d2 = tri_xyz[:, 2, :] - p0
    nx_l, nx_r = d1[:, 2] * d2[:, 1], d2[:, 2] * d1[:, 1]
    ny_l, ny_r = d1[:, 0] * d2[:, 2], d2[:, 0] * d1[:, 2]
    a_l, a_r = d1[:, 0] * d2[:, 1], d2[:, 0] * d1[:, 1]
    nx, ny, a2 = nx_l - nx_r, ny_l - ny_r, a_l - a_r
    gam = 16 * EPS
    enx = gam * (np.abs(nx_l) + np.abs(nx_r))
    eny = gam * (np.abs(ny_l) + np.abs(ny_r))
    ea = gam * (np.abs(a_l) + np.abs(a_r))
    n_lo = np.maximum(np.abs(nx) - enx, 0.0) ** 2 + np.maximum(np.abs(ny) - eny, 0.0) ** 2
    n_hi = (np.abs(nx) + enx) ** 2 + (np.abs(ny) + eny) ** 2
    t2 = t * t
    a_lo = np.maximum(a2 - ea, 0.0)
    a_hi = a2 + ea
    exceeds = n_lo * (1 - 1e-12) > t2 * a_hi**2 * (1 + 1e-12)
    within = n_hi * (1 + 1e-12) < t2 * a_lo**2 * (1 - 1e-12)
    unsure = ~exceeds & ~within
    out = exceeds.copy()
    tq = Fraction(t)
    for k in np.nonzero(unsure)[0]:
        q = [[Fraction(float(v)) for v in row] for row in tri_xyz[k]]
        e1 = [q[1][i] - q[0][i] for i in range(3)]
        e2 = [q[2][i] - q[0][i] for i in range(3)]
        qx = e1[2] * e2[1] - e2[2] * e1[1]
        qy = e1[0] * e2[2] - e2[0] * e1[2]
        qa = e1[0] * e2[1] - e2[0] * e1[1]
        out[k] = qx * qx + qy * qy > tq * tq * qa * qa
        if stats is not None:
            stats.slope_exact += 1
    return out
