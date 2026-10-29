"""Placement engine: policy minimum_clearance_vertical_lift (CONTRACTS.md sections 4-6).

For each Module 01 table, in Module 01 order:
1. Candidate triangles come from an STR-tree over triangle bounding boxes, and candidate
   boundary segments from an STR-tree over the prepared coverage boundary.
2. Coverage (exact): covered iff no boundary segment meets the open footprint and the
   footprint centroid lies in a triangle. Otherwise the table is unknown_ground.
3. Overlay points: footprint corners (lowest-index point location), TIN vertices in the
   closed footprint, and proper crossings of candidate-triangle edges with footprint edges.
   L = max(G - d tan(beta)) + c + s over them; the maximum of a piecewise-linear function
   over the footprint is attained there.
4. Slope set: triangles whose interior meets the footprint interior (exact). A table is
   infeasible on slope iff some g^2 > t^2 exactly.
5. Supports at their exact rational positions; above-ground height = top - ground. A
   height within 1e-9 m of the limit is re-decided with L and the height in rationals.

Elevations are doubles in the layout's anchor-translated frame; plan decisions use the
represented world coordinates. Areas (shapely/GEOS) are informative.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable

import numpy as np
import shapely

from solar_layout.jsonio import canonical_dumps

from . import policy
from .predicates import (
    ExactStats,
    gradient_exceeds,
    locate_rational,
    point_in_closed_convex,
    proper_crossings,
    segments_meet_open_convex,
    triangles_meet_open_convex,
)
from .source import SourceLayout

UNKNOWN = "unknown_ground"
PLACED = "placed"
INFEASIBLE = "infeasible"
R_COVER = "footprint_not_fully_covered"
R_SLOPE = "ground_slope_exceeds_limit"
R_SUPPORT = "support_above_ground_exceeds_limit"


@dataclass
class TerrainArrays:
    terrain_id: str
    terrain_digest: str
    frame: dict[str, Any]
    vertical: dict[str, Any]
    vertices: np.ndarray
    triangles: np.ndarray
    boundary_segments: np.ndarray


@dataclass
class Placement:
    tables: list[dict[str, Any]]
    modules: list[dict[str, Any]]
    supports: list[dict[str, Any]]
    counts: dict[str, Any]
    statistics: dict[str, Any]
    diagnostics: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


class _Ctx:
    def __init__(self, src: SourceLayout, ter: TerrainArrays, req: dict[str, Any]):
        self.src = src
        self.V = np.asarray(ter.vertices, dtype=np.float64)
        self.T = np.asarray(ter.triangles, dtype=np.int64)
        self.segs = np.asarray(ter.boundary_segments, dtype=np.int64)
        self.origin = np.array(src.origin, dtype=np.float64)
        self.Vt = self.V[:, :2] - self.origin  # anchor-translated plan coordinates
        self.Z = self.V[:, 2]
        self.u = np.array(src.u, dtype=np.float64)
        self.v = np.array(src.v, dtype=np.float64)
        self.tanb = src.H / src.D if src.H != 0.0 else 0.0
        self.c = req["placement"]["minimum_clearance_m"]
        self.s = req["placement"]["structure_depth_m"]
        self.points = req["supports"]["points_ad_m"]
        self.slope_limit = req["limits"]["max_ground_slope_deg"]
        self.t_slope = math.tan(math.radians(self.slope_limit))
        self.support_limit = req["limits"]["max_support_above_ground_m"]
        self.stats = ExactStats()


# ---- candidate selection --------------------------------------------------------------------


def _group(pairs: np.ndarray, n_groups: int, mapping: np.ndarray) -> list[np.ndarray]:
    """Group (input, tree) query pairs by input; each group sorted by global index."""
    order = np.lexsort((mapping[pairs[1]], pairs[0]))
    inp = pairs[0][order]
    glob = mapping[pairs[1]][order]
    bounds = np.searchsorted(inp, np.arange(n_groups + 1))
    return [glob[bounds[k] : bounds[k + 1]] for k in range(n_groups)]


def _candidates(ctx: _Ctx, footprints: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray], int]:
    n = len(footprints)
    lo = footprints.reshape(-1, 2).min(axis=0)
    hi = footprints.reshape(-1, 2).max(axis=0)
    txy = ctx.V[ctx.T][:, :, :2]
    tmin, tmax = txy.min(axis=1), txy.max(axis=1)
    near = (tmax[:, 0] >= lo[0]) & (tmin[:, 0] <= hi[0]) & (tmax[:, 1] >= lo[1]) & (tmin[:, 1] <= hi[1])
    sub = np.nonzero(near)[0]
    polys = shapely.polygons(footprints)
    if len(sub):
        tree = shapely.STRtree(shapely.box(tmin[sub, 0], tmin[sub, 1], tmax[sub, 0], tmax[sub, 1]))
        tri_c = _group(tree.query(polys), n, sub)
    else:
        tri_c = [np.zeros(0, dtype=np.int64) for _ in range(n)]
    if len(ctx.segs):
        seg_tree = shapely.STRtree(shapely.linestrings(ctx.V[ctx.segs][:, :, :2]))
        seg_c = _group(seg_tree.query(polys), n, np.arange(len(ctx.segs)))
    else:
        seg_c = [np.zeros(0, dtype=np.int64) for _ in range(n)]
    return tri_c, seg_c, int(len(sub))


# ---- per-table geometry ---------------------------------------------------------------------


def _plane_value(ctx: _Ctx, tri: int, p_t: np.ndarray) -> float:
    """Barycentric elevation of triangle `tri` at translated plan point p_t."""
    i0, i1, i2 = ctx.T[tri]
    p0, p1, p2 = ctx.Vt[i0], ctx.Vt[i1], ctx.Vt[i2]
    e1, e2, q = p1 - p0, p2 - p0, p_t - p0
    det = e1[0] * e2[1] - e1[1] * e2[0]
    l1 = (q[0] * e2[1] - q[1] * e2[0]) / det
    l2 = (e1[0] * q[1] - e1[1] * q[0]) / det
    z0 = ctx.Z[i0]
    return float(z0 + l1 * (ctx.Z[i1] - z0) + l2 * (ctx.Z[i2] - z0))


def _plane_value_exact(ctx: _Ctx, tri: int, p: tuple[Fraction, Fraction]) -> Fraction:
    pts = [[Fraction(float(c)) for c in ctx.V[i]] for i in ctx.T[tri]]
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = pts
    det = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
    qx, qy = p[0] - x0, p[1] - y0
    l1 = (qx * (y2 - y0) - qy * (x2 - x0)) / det
    l2 = ((x1 - x0) * qy - (y1 - y0) * qx) / det
    return z0 + l1 * (z1 - z0) + l2 * (z2 - z0)


def _rational_point(F: np.ndarray, a: float, d: float, W: float, D: float) -> tuple[Fraction, Fraction]:
    c0 = [Fraction(float(x)) for x in F[0]]
    c1 = [Fraction(float(x)) for x in F[1]]
    c3 = [Fraction(float(x)) for x in F[3]]
    fa, fd = Fraction(a) / Fraction(W), Fraction(d) / Fraction(D)
    return (c0[0] + fa * (c1[0] - c0[0]) + fd * (c3[0] - c0[0]), c0[1] + fa * (c1[1] - c0[1]) + fd * (c3[1] - c0[1]))


def _unique_edges(tris: np.ndarray) -> np.ndarray:
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    return np.unique(np.sort(e, axis=1), axis=0)


class _Overlay:
    """Overlay points of one covered table: world xy, translated xy, ground z, and the
    exact description needed for the rational recomputation."""

    def __init__(self) -> None:
        self.world: list[np.ndarray] = []
        self.trans: list[np.ndarray] = []
        self.g: list[np.ndarray] = []
        self.exact: list[tuple] = []  # ("corner", k, tri) | ("vertex", vid) | ("cross", ia, ib, k)

    def add(self, world: np.ndarray, trans: np.ndarray, g: np.ndarray, exact: list[tuple]) -> None:
        if len(g):
            self.world.append(world)
            self.trans.append(trans)
            self.g.append(g)
            self.exact.extend(exact)

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return np.concatenate(self.world), np.concatenate(self.trans), np.concatenate(self.g)


def _overlay(ctx: _Ctx, F: np.ndarray, Ft: np.ndarray, cand: np.ndarray, corner_tris: list[int]) -> _Overlay:
    ov = _Overlay()
    ov.add(F.copy(), Ft.copy(), np.array([_plane_value(ctx, t, Ft[k]) for k, t in enumerate(corner_tris)]), [("corner", k, t) for k, t in enumerate(corner_tris)])
    vids = np.unique(ctx.T[cand].reshape(-1))
    inside = point_in_closed_convex(F, ctx.V[vids, 0], ctx.V[vids, 1], ctx.stats)
    vin = vids[inside]
    ov.add(ctx.V[vin, :2], ctx.Vt[vin], ctx.Z[vin], [("vertex", int(i)) for i in vin])
    E = _unique_edges(ctx.T[cand])
    A, B = ctx.V[E[:, 0], :2], ctx.V[E[:, 1], :2]
    At, Bt = ctx.Vt[E[:, 0]], ctx.Vt[E[:, 1]]
    for k in range(4):
        fa, fb = F[k], F[(k + 1) % 4]
        cross = proper_crossings(A, B, np.broadcast_to(fa, A.shape), np.broadcast_to(fb, A.shape), ctx.stats)
        if not cross.any():
            continue
        idx = np.nonzero(cross)[0]
        fat, fbt = Ft[k], Ft[(k + 1) % 4]
        ex, ey = fbt[0] - fat[0], fbt[1] - fat[1]
        oa = ex * (At[idx, 1] - fat[1]) - ey * (At[idx, 0] - fat[0])
        ob = ex * (Bt[idx, 1] - fat[1]) - ey * (Bt[idx, 0] - fat[0])
        denom = oa - ob
        t = np.clip(np.divide(oa, denom, out=np.zeros_like(oa), where=denom != 0), 0.0, 1.0)
        za, zb = ctx.Z[E[idx, 0]], ctx.Z[E[idx, 1]]
        world = A[idx] + t[:, None] * (B[idx] - A[idx])
        trans = At[idx] + t[:, None] * (Bt[idx] - At[idx])
        ov.add(world, trans, za + t * (zb - za), [("cross", int(E[i, 0]), int(E[i, 1]), k) for i in idx])
    return ov


def _exact_overlay_max(ctx: _Ctx, F: np.ndarray, ov: _Overlay, tanb: Fraction) -> Fraction:
    """max(G - d tan(beta)) over the overlay points in rational arithmetic."""
    c0 = [Fraction(float(x)) for x in F[0]]
    vx, vy = Fraction(float(ctx.v[0])), Fraction(float(ctx.v[1]))
    best = None
    for item in ov.exact:
        if item[0] == "corner":
            _, k, tri = item
            p = (Fraction(float(F[k, 0])), Fraction(float(F[k, 1])))
            g = _plane_value_exact(ctx, tri, p)
        elif item[0] == "vertex":
            x, y, z = (Fraction(float(c)) for c in ctx.V[item[1]])
            p, g = (x, y), z
        else:
            _, ia, ib, k = item
            a = [Fraction(float(c)) for c in ctx.V[ia]]
            b = [Fraction(float(c)) for c in ctx.V[ib]]
            fa = [Fraction(float(c)) for c in F[k]]
            fb = [Fraction(float(c)) for c in F[(k + 1) % 4]]
            oa = (fb[0] - fa[0]) * (a[1] - fa[1]) - (fb[1] - fa[1]) * (a[0] - fa[0])
            ob = (fb[0] - fa[0]) * (b[1] - fa[1]) - (fb[1] - fa[1]) * (b[0] - fa[0])
            t = oa / (oa - ob)
            p = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            g = a[2] + t * (b[2] - a[2])
        d = (p[0] - c0[0]) * vx + (p[1] - c0[1]) * vy
        w = g - d * tanb
        if best is None or w > best:
            best = w
    return best


def _clip_area_exact(poly: list[tuple[Fraction, Fraction]], tri: list[tuple[Fraction, Fraction]]) -> Fraction:
    """Exact area of a convex polygon clipped by a counter-clockwise triangle."""
    out = poly
    for e in range(3):
        a, b = tri[e], tri[(e + 1) % 3]
        if not out:
            break
        src, out = out, []
        for i in range(len(src)):
            p, q = src[i], src[(i + 1) % len(src)]
            sp = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
            sq = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
            if sp >= 0:
                out.append(p)
            if (sp > 0 > sq) or (sp < 0 < sq):
                t = sp / (sp - sq)
                out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    area = Fraction(0)
    for i in range(len(out)):
        p, q = out[i], out[(i + 1) % len(out)]
        area += p[0] * q[1] - q[0] * p[1]
    return area / 2


def _place_table(ctx: _Ctx, seq: int, rec: dict[str, Any], cand: np.ndarray, segc: np.ndarray, diag: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], float]:
    src = ctx.src
    F = np.array(rec["footprint_xy_m"], dtype=np.float64)
    Ft = F - ctx.origin
    out: dict[str, Any] = {
        "seq": seq,
        "table_id": rec["table_id"],
        "status": None,
        "reasons": [],
        "module_count": rec["module_count"],
        "footprint_xy_m": rec["footprint_xy_m"],
    }
    diag["candidate_triangles_total"] += int(len(cand))
    diag["candidate_triangles_max_per_table"] = max(diag["candidate_triangles_max_per_table"], int(len(cand)))
    diag["boundary_segment_candidates_total"] += int(len(segc))
    txy = ctx.V[ctx.T[cand]][:, :, :2] if len(cand) else np.zeros((0, 3, 2))

    # coverage, exact and topological
    covered = len(cand) > 0
    if covered and len(segc):
        covered = not segments_meet_open_convex(ctx.V[ctx.segs[segc]][:, :, :2], F, ctx.stats).any()
    if covered:
        cen = tuple(sum(Fraction(float(F[k, i])) for k in range(4)) / 4 for i in range(2))
        covered = locate_rational(txy, cand, cen, (float(F[:, 0].mean()), float(F[:, 1].mean())), ctx.stats) >= 0

    # triangles whose interior meets the footprint interior: areas, slope, gradient
    meets = triangles_meet_open_convex(txy, F, ctx.stats) if len(cand) else np.zeros(0, dtype=bool)
    sl = cand[meets]
    fp_t = shapely.polygons(Ft)
    pieces = np.zeros(len(sl))
    if len(sl):
        # triangles with every vertex in the closed footprint (exact) count whole; GEOS clips the rest
        tv = ctx.T[sl]
        whole = point_in_closed_convex(F, ctx.V[tv, 0], ctx.V[tv, 1], ctx.stats).all(axis=1)
        tt = ctx.Vt[tv]
        pieces[whole] = 0.5 * ((tt[whole, 1, 0] - tt[whole, 0, 0]) * (tt[whole, 2, 1] - tt[whole, 0, 1]) - (tt[whole, 2, 0] - tt[whole, 0, 0]) * (tt[whole, 1, 1] - tt[whole, 0, 1]))
        if (~whole).any():
            pieces[~whole] = shapely.area(shapely.intersection(shapely.polygons(tt[~whole]), fp_t))
    covered_area = float(pieces.sum())
    footprint_area = float(shapely.area(fp_t))

    if not covered:
        uncovered = footprint_area - covered_area
        if not uncovered > 0.0:
            # The exact coverage test failed but the double areas cannot show the gap.
            fq = [(Fraction(float(x)), Fraction(float(y))) for x, y in F]
            exact_cov = sum((_clip_area_exact(fq, [(Fraction(float(ctx.V[i, 0])), Fraction(float(ctx.V[i, 1]))) for i in ctx.T[t]]) for t in sl), Fraction(0))
            exact_fp = sum((fq[i][0] * fq[(i + 1) % 4][1] - fq[(i + 1) % 4][0] * fq[i][1] for i in range(4)), Fraction(0)) / 2
            uncovered = float(exact_fp - exact_cov)
            covered_area = float(exact_cov)
            diag["exact_area_fallbacks"] += 1
        out.update(status=UNKNOWN, reasons=[R_COVER], covered_area_m2=covered_area, uncovered_area_m2=uncovered)
        return out, [], 0.0

    out.update(covered_area_m2=covered_area, uncovered_area_m2=0.0)
    corner_tris = []
    for k in range(4):
        t = locate_rational(txy, cand, (Fraction(float(F[k, 0])), Fraction(float(F[k, 1]))), (float(F[k, 0]), float(F[k, 1])), ctx.stats)
        assert t >= 0, "a covered footprint corner must lie in a triangle"
        corner_tris.append(t)
    ov = _overlay(ctx, F, Ft, cand, corner_tris)
    world, trans, g = ov.arrays()
    rel = trans - Ft[0]
    d = rel @ ctx.v
    a = rel @ ctx.u
    w = g - d * ctx.tanb
    best = int(np.lexsort((a, d, -w))[0])
    L = float(w[best] + ctx.c + ctx.s)
    clear = L + d * ctx.tanb - ctx.s - g
    diag["overlay_points_total"] += int(len(g))

    # slope set
    tri_xyz = ctx.V[ctx.T[sl]]
    p0 = np.concatenate([ctx.Vt[ctx.T[sl, 0]], ctx.Z[ctx.T[sl, 0], None]], axis=1)
    p1 = np.concatenate([ctx.Vt[ctx.T[sl, 1]], ctx.Z[ctx.T[sl, 1], None]], axis=1)
    p2 = np.concatenate([ctx.Vt[ctx.T[sl, 2]], ctx.Z[ctx.T[sl, 2], None]], axis=1)
    d1, d2 = p1 - p0, p2 - p0
    a2 = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    gx = (d1[:, 2] * d2[:, 1] - d2[:, 2] * d1[:, 1]) / a2
    gy = (d1[:, 0] * d2[:, 2] - d2[:, 0] * d1[:, 2]) / a2
    gmag = np.hypot(gx, gy)
    slope_exceeds = bool(gradient_exceeds(tri_xyz, ctx.t_slope, ctx.stats).any())
    total = pieces.sum()
    mean_g = np.array([(pieces * gx).sum() / total, (pieces * gy).sum() / total])

    # supports
    supports = []
    support_exceeds = False
    exact_L = None
    tanb_q = Fraction(src.H) / Fraction(src.D) if src.H != 0.0 else Fraction(0)
    limit = ctx.support_limit
    for k, (sa, sd) in enumerate(ctx.points):
        pw = F[0] + (sa / src.W) * (F[1] - F[0]) + (sd / src.D) * (F[3] - F[0])
        pq = _rational_point(F, sa, sd, src.W, src.D)
        tri = locate_rational(txy, cand, pq, (float(pw[0]), float(pw[1])), ctx.stats)
        assert tri >= 0, "a support inside a covered footprint must lie in a triangle"
        ground = _plane_value(ctx, tri, pw - ctx.origin)
        top = L + sd * ctx.tanb - ctx.s
        height = top - ground
        if height - limit > policy.SUPPORT_LIMIT_BAND_M:
            exceeds = True
        elif height - limit < -policy.SUPPORT_LIMIT_BAND_M:
            exceeds = False
        else:
            if exact_L is None:
                exact_L = _exact_overlay_max(ctx, F, ov, tanb_q) + Fraction(ctx.c) + Fraction(ctx.s)
            h_exact = exact_L + Fraction(sd) * tanb_q - Fraction(ctx.s) - _plane_value_exact(ctx, tri, pq)
            exceeds = h_exact > Fraction(limit)
            ctx.stats.support_band_exact += 1
        support_exceeds |= exceeds
        supports.append(
            {
                "support_id": f"S_{rec['table_id']}_{k}",
                "table_id": rec["table_id"],
                "a_m": sa,
                "d_m": sd,
                "xy_m": [float(pw[0]), float(pw[1])],
                "ground_z_m": ground,
                "top_z_m": top,
                "above_ground_m": height,
            }
        )

    reasons = ([R_SLOPE] if slope_exceeds else []) + ([R_SUPPORT] if support_exceeds else [])
    out.update(
        status=INFEASIBLE if reasons else PLACED,
        reasons=reasons,
        lower_edge_z_m=L,
        upper_edge_z_m=L + src.D * ctx.tanb,
        vertical_lift_m=L - src.h0,
        min_clearance_m=float(clear.min()),
        min_clearance_at_xy_m=[float(world[best, 0]), float(world[best, 1])],
        max_clearance_m=float(clear.max()),
        max_ground_slope_deg=float(math.degrees(math.atan(float(gmag.max())))),
        mean_ground_gradient_uv=[float(mean_g @ ctx.u), float(mean_g @ ctx.v)],
    )
    return out, supports, L - src.h0


def place(src: SourceLayout, ter: TerrainArrays, req: dict[str, Any], check: Callable[[str], None]) -> Placement:
    ctx = _Ctx(src, ter, req)
    footprints = np.array([t["footprint_xy_m"] for t in src.tables], dtype=np.float64).reshape(-1, 4, 2)
    tri_c, seg_c, indexed = _candidates(ctx, footprints)
    check("candidate selection")
    diag = {
        "triangles_indexed": indexed,
        "candidate_triangles_total": 0,
        "candidate_triangles_max_per_table": 0,
        "boundary_segment_candidates_total": 0,
        "overlay_points_total": 0,
        "exact_area_fallbacks": 0,
        "candidate_selection": "STR-tree over triangle bounding boxes (triangles whose box meets the layout's box), queried with each footprint",
    }
    tables: list[dict[str, Any]] = []
    supports: list[dict[str, Any]] = []
    lift: dict[str, float] = {}
    for seq, rec in enumerate(src.tables):
        trec, sups, delta = _place_table(ctx, seq, rec, tri_c[seq], seg_c[seq], diag)
        tables.append(trec)
        if trec["status"] == PLACED:
            lift[trec["table_id"]] = delta
        if trec["status"] != UNKNOWN:
            supports.extend(sups)
        check("table placement")
    for k, s in enumerate(supports):
        supports[k] = {"seq": k, **s}

    modules: list[dict[str, Any]] = []
    power = 0.0
    for m in src.modules:
        delta = lift.get(m["table_id"])
        if delta is None:
            continue
        modules.append(
            {
                "seq": len(modules),
                "module_id": m["module_id"],
                "table_id": m["table_id"],
                "corners_xyz_m": [[x, y, z + delta] for x, y, z in m["corners_xyz_m"]],
            }
        )
        power += m["power_wp"]
    check("module records")

    status_count = {s: sum(1 for t in tables if t["status"] == s) for s in (PLACED, UNKNOWN, INFEASIBLE)}
    counts = {
        "tables": len(tables),
        "placed_tables": status_count[PLACED],
        "unknown_ground_tables": status_count[UNKNOWN],
        "infeasible_tables": status_count[INFEASIBLE],
        "placed_modules": len(modules),
        "placed_dc_capacity_kwp": power / 1000.0,
        "supports": len(supports),
    }
    measured = [t for t in tables if t["status"] != UNKNOWN]

    def rng(key: str) -> list[float] | None:
        vals = [t[key] for t in measured]
        return [min(vals), max(vals)] if vals else None

    statistics = {
        "lower_edge_z_m_range": rng("lower_edge_z_m"),
        "vertical_lift_m_range": rng("vertical_lift_m"),
        "min_clearance_m_range": rng("min_clearance_m"),
        "max_clearance_m_range": rng("max_clearance_m"),
        "max_ground_slope_deg": max((t["max_ground_slope_deg"] for t in measured), default=None),
        "support_above_ground_m_range": [min(s["above_ground_m"] for s in supports), max(s["above_ground_m"] for s in supports)] if supports else None,
        "covered_area_m2_total": sum(t["covered_area_m2"] for t in tables),
        "uncovered_area_m2_total": sum(t["uncovered_area_m2"] for t in tables),
        "slope_limit_tan": ctx.t_slope,
    }
    diag["exact_arithmetic"] = ctx.stats.as_dict()
    warnings = []
    if status_count[UNKNOWN]:
        warnings.append(f"{status_count[UNKNOWN]} of {len(tables)} tables are on unknown ground (footprint not wholly inside the surveyed surface) and are not placed")
    if status_count[INFEASIBLE]:
        warnings.append(f"{status_count[INFEASIBLE]} of {len(tables)} tables exceed a slope or support-height limit and are not placed; their elevations and supports are reported")
    return Placement(tables=tables, modules=modules, supports=supports, counts=counts, statistics=statistics, diagnostics=diag, warnings=warnings)


PAYLOAD_SUMMARY_KEYS = ("schema_version", "placement_id", "source_layout", "terrain", "parameters_digest", "frame", "vertical", "z_kind", "policy", "counts")


def payload_digest(summary: dict[str, Any], tables: list[dict[str, Any]], modules: list[dict[str, Any]], supports: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    h.update(canonical_dumps({k: summary[k] for k in PAYLOAD_SUMMARY_KEYS}).encode())
    for group in (tables, modules, supports):
        for rec in group:
            h.update(b"\n")
            h.update(canonical_dumps(rec).encode())
    return h.hexdigest()

