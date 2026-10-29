"""Independent verifier of a terrain placement (CONTRACTS.md sections 4-6, PLAN.md section 8).

It shares no geometry code with the engine: it does not import engine, predicates,
surface or request (import-boundary test), and it reaches its conclusions by different
routes:

* candidates: its own uniform grid over triangle bounding boxes (the engine uses an STR-tree);
* exact arithmetic: a deliberately loose double filter (relative 1e-12) and
  fractions.Fraction, not the engine's expansion arithmetic;
* coverage: it rebuilds the boundary from the candidate triangles, splitting edges at
  candidate vertices, and tests each boundary piece against the open footprint by exact
  parametric clipping (the engine uses separating lines and a prepared boundary);
* elevations: it clips every candidate triangle against the footprint (Sutherland-Hodgman)
  and evaluates the clipped polygon vertices (the engine enumerates corner, vertex and
  edge-crossing points); its own areas come from the same clipping;
* supports: its own exact point location;
* digests and identities: recomputed here.

It consumes records exactly as stored: the Module 01 summary and records (through the
published service operations), the stored terrain arrays and the placement as returned.
"""

from __future__ import annotations

import hashlib
import math
import re
from fractions import Fraction
from typing import Any, Iterable

import numpy as np

from solar_layout.jsonio import canonical_dumps, digest_of

from . import ALGORITHM_VERSION, POLICY_VERSION, RESULT_SCHEMA, policy
from .schemas import RESULT, validator

CHECKS = (
    "schema",
    "contract_fields",
    "identity",
    "source_linkage",
    "datum",
    "status_records",
    "coverage",
    "clearance",
    "lift_policy",
    "clearance_report",
    "elevations",
    "slope",
    "supports",
    "module_geometry",
    "totals",
    "payload_integrity",
)
MAX_FAILURES = 5
MEASURED = ("lower_edge_z_m", "upper_edge_z_m", "vertical_lift_m", "min_clearance_m", "min_clearance_at_xy_m", "max_clearance_m", "max_ground_slope_deg", "mean_ground_gradient_uv")


class _Checks:
    def __init__(self) -> None:
        self.data = {name: {"ok": True, "failures": []} for name in CHECKS}

    def fail(self, name: str, message: str) -> None:
        entry = self.data[name]
        entry["ok"] = False
        if len(entry["failures"]) < MAX_FAILURES:
            entry["failures"].append(message)

    def require(self, name: str, cond: bool, message: str) -> bool:
        if not cond:
            self.fail(name, message)
        return bool(cond)


def _close(a: float, b: float, tol: float) -> bool:
    return abs(float(a) - float(b)) <= tol


# ---- exact arithmetic (own) ----------------------------------------------------------------


class _Exact:
    def __init__(self) -> None:
        self.rational = 0

    def orient(self, ax, ay, bx, by, cx, cy) -> np.ndarray:
        """Exact sign of (b - a) x (c - a) for broadcastable double arrays."""
        ax, ay, bx, by, cx, cy = np.broadcast_arrays(*(np.asarray(v, dtype=np.float64) for v in (ax, ay, bx, by, cx, cy)))
        p1, p2, q1, q2 = bx - ax, cy - ay, by - ay, cx - ax
        left, right = p1 * p2, q1 * q2
        det = left - right
        mag = np.abs(left) + np.abs(right)
        out = np.sign(det).astype(np.int8)
        zero = ((p1 == 0) | (p2 == 0)) & ((q1 == 0) | (q2 == 0))
        out[zero] = 0
        sure = zero | ((mag > 1e-200) & (np.abs(det) > 1e-12 * mag))
        for k in zip(*np.nonzero(~sure)):
            fa = [Fraction(float(v[k])) for v in (ax, ay, bx, by, cx, cy)]
            d = (fa[2] - fa[0]) * (fa[5] - fa[1]) - (fa[3] - fa[1]) * (fa[4] - fa[0])
            out[k] = (d > 0) - (d < 0)
            self.rational += 1
        return out


def _q(x: float) -> Fraction:
    return Fraction(float(x))


def _cross_q(a, b, c) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


# ---- own uniform grid ----------------------------------------------------------------------


class _Grid:
    def __init__(self, V: np.ndarray, T: np.ndarray, region: tuple[float, float, float, float]):
        txy = V[T][:, :, :2]
        tmin, tmax = txy.min(axis=1), txy.max(axis=1)
        x0, y0, x1, y1 = region
        near = (tmax[:, 0] >= x0) & (tmin[:, 0] <= x1) & (tmax[:, 1] >= y0) & (tmin[:, 1] <= y1)
        self.ids = np.nonzero(near)[0]
        self.x0, self.y0 = x0, y0
        n = max(len(self.ids), 1)
        width, height = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
        ext = np.maximum(tmax[self.ids] - tmin[self.ids], 0.0)
        cell = max(math.sqrt(width * height / n), float(np.median(ext.max(axis=1))) if len(self.ids) else 1.0, 1e-6)
        while True:
            self.cell = cell
            self.nx = int(width // cell) + 1
            self.ny = int(height // cell) + 1
            lo = self._cell(tmin[self.ids])
            hi = self._cell(tmax[self.ids])
            span = (hi[:, 0] - lo[:, 0] + 1) * (hi[:, 1] - lo[:, 1] + 1)
            if span.sum() <= 16 * n + 100_000:
                break
            cell *= 2.0
        rep = np.repeat(np.arange(len(self.ids)), span)
        offs = np.arange(len(rep)) - np.repeat(np.cumsum(span) - span, span)
        w = np.repeat(hi[:, 0] - lo[:, 0] + 1, span)
        cx = np.repeat(lo[:, 0], span) + offs % w
        cy = np.repeat(lo[:, 1], span) + offs // w
        key = cy * self.nx + cx
        order = np.argsort(key, kind="stable")
        self.key = key[order]
        self.members = self.ids[rep[order]]
        self.assignments = int(len(rep))

    def _cell(self, xy: np.ndarray) -> np.ndarray:
        cx = np.clip(((xy[:, 0] - self.x0) // self.cell).astype(np.int64), 0, self.nx - 1)
        cy = np.clip(((xy[:, 1] - self.y0) // self.cell).astype(np.int64), 0, self.ny - 1)
        return np.stack([cx, cy], axis=1)

    def query(self, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        a = self._cell(lo[None, :])[0]
        b = self._cell(hi[None, :])[0]
        cells = (np.arange(a[1], b[1] + 1)[:, None] * self.nx + np.arange(a[0], b[0] + 1)[None, :]).reshape(-1)
        left = np.searchsorted(self.key, cells, side="left")
        right = np.searchsorted(self.key, cells, side="right")
        if (right > left).any():
            got = np.concatenate([self.members[l:r] for l, r in zip(left, right) if r > l])
            return np.unique(got)
        return np.zeros(0, dtype=np.int64)


# ---- per-table geometry (own) --------------------------------------------------------------


def _clip(poly: list[tuple[float, float]], quad: np.ndarray) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of a polygon by a counter-clockwise convex quad (doubles)."""
    out = poly
    for k in range(4):
        if not out:
            return out
        ax, ay = quad[k]
        bx, by = quad[(k + 1) % 4]
        src, out = out, []
        n = len(src)
        for i in range(n):
            px, py = src[i]
            qx, qy = src[(i + 1) % n]
            sp = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
            sq = (bx - ax) * (qy - ay) - (by - ay) * (qx - ax)
            if sp >= 0:
                out.append((px, py))
            if (sp > 0 and sq < 0) or (sp < 0 and sq > 0):
                t = sp / (sp - sq)
                out.append((px + t * (qx - px), py + t * (qy - py)))
    return out


def _clip_q(poly: list[tuple[Fraction, Fraction]], tri: list[tuple[Fraction, Fraction]]) -> list[tuple[Fraction, Fraction]]:
    out = poly
    for e in range(3):
        if not out:
            return out
        a, b = tri[e], tri[(e + 1) % 3]
        src, out = out, []
        for i in range(len(src)):
            p, q = src[i], src[(i + 1) % len(src)]
            sp, sq = _cross_q(a, b, p), _cross_q(a, b, q)
            if sp >= 0:
                out.append(p)
            if (sp > 0 > sq) or (sp < 0 < sq):
                t = sp / (sp - sq)
                out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _area(poly) -> Any:
    s = 0
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        s += p[0] * q[1] - q[0] * p[1]
    return s / 2


def _segment_meets_open_quad(p, q, quad_q) -> bool:
    """Exact: does the closed segment pq meet the open convex quad? Parametric clipping of
    t in [0, 1] against the four open half-planes."""
    lo, hi = Fraction(0), Fraction(1)
    for k in range(4):
        a, b = quad_q[k], quad_q[(k + 1) % 4]
        f0, f1 = _cross_q(a, b, p), _cross_q(a, b, q)
        slope = f1 - f0
        if slope == 0:
            if f0 <= 0:
                return False
            continue
        root = -f0 / slope
        if slope > 0:
            lo = max(lo, root)
        else:
            hi = min(hi, root)
    return lo < hi


class _Table:
    """Everything the verifier derives for one table."""

    def __init__(self, ctx: "_Ctx", rec01: dict[str, Any]):
        self.ctx = ctx
        F = np.array(rec01["footprint_xy_m"], dtype=np.float64)
        self.F = F
        self.Fq = [(_q(x), _q(y)) for x, y in F]
        self.cand = ctx.grid.query(F.min(axis=0), F.max(axis=0))
        ctx.cand_total += len(self.cand)
        ctx.cand_max = max(ctx.cand_max, len(self.cand))
        self.Ft = F - ctx.origin
        self.footprint_area = float(_area([tuple(p) for p in self.Ft]))
        ids = ctx.T[self.cand]
        self.tw = ctx.V[ids]  # (n, 3, 3) world
        self.tt = ctx.Vt[ids]  # (n, 3, 2) translated
        self.tmin = self.tw[:, :, :2].min(axis=1) if len(self.cand) else np.zeros((0, 2))
        self.tmax = self.tw[:, :, :2].max(axis=1) if len(self.cand) else np.zeros((0, 2))
        # plane z = z0 - (nx (x - x0) + ny (y - y0)) / nz in translated coordinates
        if len(self.cand):
            p0 = np.concatenate([self.tt[:, 0], self.tw[:, 0, 2:]], axis=1)
            p1 = np.concatenate([self.tt[:, 1], self.tw[:, 1, 2:]], axis=1)
            p2 = np.concatenate([self.tt[:, 2], self.tw[:, 2, 2:]], axis=1)
            self.normal = np.cross(p1 - p0, p2 - p0)
            self.p0 = p0
        else:
            self.normal = np.zeros((0, 3))
            self.p0 = np.zeros((0, 3))

    def _pos(self, t: int) -> int:
        return int(np.searchsorted(self.cand, t))

    def ground(self, t: int, p_t: np.ndarray) -> float:
        k = self._pos(t)
        n, p0 = self.normal[k], self.p0[k]
        return float(p0[2] - (n[0] * (p_t[0] - p0[0]) + n[1] * (p_t[1] - p0[1])) / n[2])

    # point location ----------------------------------------------------------------------
    def locate(self, p: tuple[Fraction, Fraction], approx: tuple[float, float]) -> int:
        """Lowest-index candidate whose closed triangle contains the rational point p."""
        if len(self.cand) == 0:
            return -1
        m = 1e-6
        near = (approx[0] >= self.tmin[:, 0] - m) & (approx[0] <= self.tmax[:, 0] + m) & (approx[1] >= self.tmin[:, 1] - m) & (approx[1] <= self.tmax[:, 1] + m)
        for k in np.nonzero(near)[0]:  # candidates ascend by global index
            tq = [(_q(x), _q(y)) for x, y in self.tw[k, :, :2]]
            self.ctx.exact.rational += 1
            if all(_cross_q(tq[e], tq[(e + 1) % 3], p) >= 0 for e in range(3)):
                return int(self.cand[k])
        return -1

    # coverage --------------------------------------------------------------------------
    def covered_exactly(self) -> bool:
        """Exact coverage. Boundary pieces are rebuilt from the candidate triangles: an edge
        whose bounding box meets the footprint's and that has no exactly reversed twin among
        the candidates is split at the candidate vertices lying inside it; sub-edges without
        a reversed twin are boundary. (An edge with an exact twin lies between two triangles
        of a validated, overlap-free surface and cannot carry a vertex in its interior.)
        The footprint is covered iff no boundary piece meets its open interior and its
        centroid lies in a triangle."""
        ctx, F = self.ctx, self.F
        if len(self.cand) == 0:
            return False
        T = ctx.T[self.cand]
        starts = T.reshape(-1)
        ends = np.roll(T, -1, axis=1).reshape(-1)
        n = int(max(starts.max(), ends.max())) + 1
        keys = np.sort(starts * n + ends)
        rev = ends * n + starts
        pos = np.minimum(np.searchsorted(keys, rev), len(keys) - 1)
        A, B = ctx.V[starts, :2], ctx.V[ends, :2]
        emin, emax = np.minimum(A, B), np.maximum(A, B)
        lo, hi = F.min(axis=0), F.max(axis=0)
        relevant = (emax[:, 0] >= lo[0]) & (emin[:, 0] <= hi[0]) & (emax[:, 1] >= lo[1]) & (emin[:, 1] <= hi[1])
        lone = np.nonzero(relevant & (keys[pos] != rev))[0]
        if len(lone):
            verts = np.unique(T.reshape(-1))
            P = ctx.V[verts, :2]
            sub = []
            for e in lone:
                inbox = (P[:, 0] >= emin[e, 0]) & (P[:, 0] <= emax[e, 0]) & (P[:, 1] >= emin[e, 1]) & (P[:, 1] <= emax[e, 1])
                inbox &= (verts != starts[e]) & (verts != ends[e])
                idx = np.nonzero(inbox)[0]
                chain = [int(starts[e])]
                if len(idx):
                    on = ctx.exact.orient(A[e, 0], A[e, 1], B[e, 0], B[e, 1], P[idx, 0], P[idx, 1]) == 0
                    mids = verts[idx[on]]  # collinear, in the closed box, not an end: strictly inside
                    dvec = B[e] - A[e]
                    proj = (ctx.V[mids, 0] - A[e, 0]) * dvec[0] + (ctx.V[mids, 1] - A[e, 1]) * dvec[1]
                    chain += [int(m) for m in mids[np.argsort(proj, kind="stable")]]
                chain.append(int(ends[e]))
                sub.extend(zip(chain[:-1], chain[1:]))
            present = set(sub)
            for a, b in sub:
                if (b, a) in present:
                    continue
                pa, pb = ctx.V[a, :2], ctx.V[b, :2]
                if max(pa[0], pb[0]) < lo[0] or min(pa[0], pb[0]) > hi[0] or max(pa[1], pb[1]) < lo[1] or min(pa[1], pb[1]) > hi[1]:
                    continue
                ctx.exact.rational += 1
                if _segment_meets_open_quad((_q(pa[0]), _q(pa[1])), (_q(pb[0]), _q(pb[1])), self.Fq):
                    return False
        cen = (sum(c[0] for c in self.Fq) / 4, sum(c[1] for c in self.Fq) / 4)
        return self.locate(cen, (float(F[:, 0].mean()), float(F[:, 1].mean()))) >= 0

    # clipping ----------------------------------------------------------------------------
    def pieces(self) -> tuple[list[tuple[int, np.ndarray, float]], np.ndarray]:
        """(triangle, clipped polygon in translated coordinates, area) for each candidate
        whose double clip is a polygon, plus a mask of candidates that are clearly apart
        from the footprint (more than 1e-9 m outside one footprint edge line). Triangles
        more than 1e-9 m inside every edge line are taken whole; the rest are clipped."""
        n = len(self.cand)
        if n == 0:
            return [], np.zeros(0, dtype=bool)
        quad = self.Ft
        side = np.empty((n, 4, 3))
        for k in range(4):
            a, b = quad[k], quad[(k + 1) % 4]
            ex, ey = b[0] - a[0], b[1] - a[1]
            side[:, k, :] = (ex * (self.tt[:, :, 1] - a[1]) - ey * (self.tt[:, :, 0] - a[0])) / math.hypot(ex, ey)
        margin = 1e-9
        inside = (side > margin).all(axis=(1, 2))
        apart = (side < -margin).all(axis=2).any(axis=1)
        tt = self.tt
        whole = 0.5 * ((tt[:, 1, 0] - tt[:, 0, 0]) * (tt[:, 2, 1] - tt[:, 0, 1]) - (tt[:, 2, 0] - tt[:, 0, 0]) * (tt[:, 1, 1] - tt[:, 0, 1]))
        out = []
        for k in np.nonzero(~apart)[0]:
            if inside[k]:
                out.append((int(self.cand[k]), tt[k], float(whole[k])))
                continue
            clipped = _clip([tuple(p) for p in tt[k]], quad)
            if len(clipped) >= 3:
                out.append((int(self.cand[k]), np.array(clipped), float(_area(clipped))))
        return out, apart

    def interior_meets(self, t: int, approx_area: float) -> bool:
        """Exact: does triangle t's interior meet the footprint interior? Clear areas are
        accepted from the double clipping; small or empty ones are re-clipped in rationals."""
        if approx_area > 1e-10:
            return True
        tri = [(_q(x), _q(y)) for x, y in self.ctx.V[self.ctx.T[t], :2]]
        self.ctx.exact.rational += 1
        return _area(_clip_q(list(self.Fq), tri)) > 0

    def slope_exceeds_any(self, ids: np.ndarray) -> bool:
        """Exact: is g^2 > t^2 for any of the triangles (represented world coordinates)?
        A relative margin of 1e-6 on the double g^2 decides clear cases."""
        ctx = self.ctx
        P = ctx.V[ctx.T[ids]]
        n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        g2 = (n[:, 0] ** 2 + n[:, 1] ** 2) / n[:, 2] ** 2
        t2 = ctx.t_slope**2
        if (g2 > t2 * (1 + 1e-6)).any():
            return True
        tq = _q(ctx.t_slope)
        for k in np.nonzero(g2 >= t2 * (1 - 1e-6))[0]:
            Q = [[_q(c) for c in row] for row in P[k]]
            e1 = [Q[1][i] - Q[0][i] for i in range(3)]
            e2 = [Q[2][i] - Q[0][i] for i in range(3)]
            nx = e1[1] * e2[2] - e1[2] * e2[1]
            ny = e1[2] * e2[0] - e1[0] * e2[2]
            nz = e1[0] * e2[1] - e1[1] * e2[0]
            ctx.exact.rational += 1
            if nx * nx + ny * ny > tq * tq * nz * nz:
                return True
        return False

    def exact_lower_edge(self) -> Fraction:
        """L in rationals: maximum of G - d tan(beta) over the exactly clipped pieces."""
        ctx = self.ctx
        c0 = self.Fq[0]
        vx, vy = _q(ctx.v[0]), _q(ctx.v[1])
        best = None
        for t in self.cand:
            pts = [[_q(c) for c in ctx.V[i]] for i in ctx.T[t]]
            poly = _clip_q(list(self.Fq), [(p[0], p[1]) for p in pts])
            if not poly:
                continue
            (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = pts
            det = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
            for px, py in poly:
                l1 = ((px - x0) * (y2 - y0) - (py - y0) * (x2 - x0)) / det
                l2 = ((x1 - x0) * (py - y0) - (y1 - y0) * (px - x0)) / det
                g = z0 + l1 * (z1 - z0) + l2 * (z2 - z0)
                w = g - ((px - c0[0]) * vx + (py - c0[1]) * vy) * ctx.tanb_q
                if best is None or w > best:
                    best = w
        return best + _q(ctx.c) + _q(ctx.s)

    def exact_ground(self, t: int, p: tuple[Fraction, Fraction]) -> Fraction:
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = [[_q(c) for c in self.ctx.V[i]] for i in self.ctx.T[t]]
        det = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
        l1 = ((p[0] - x0) * (y2 - y0) - (p[1] - y0) * (x2 - x0)) / det
        l2 = ((x1 - x0) * (p[1] - y0) - (y1 - y0) * (p[0] - x0)) / det
        return z0 + l1 * (z1 - z0) + l2 * (z2 - z0)


class _Ctx:
    def __init__(self, layout: Any, vertices: np.ndarray, triangles: np.ndarray, request: dict[str, Any]):
        self.V = np.asarray(vertices, dtype=np.float64)
        self.T = np.asarray(triangles, dtype=np.int64)
        self.origin = np.array(layout.origin, dtype=np.float64)
        self.Vt = self.V[:, :2] - self.origin
        self.Z = self.V[:, 2]
        self.u = np.array(layout.u, dtype=np.float64)
        self.v = np.array(layout.v, dtype=np.float64)
        self.W, self.D, self.H, self.h0 = layout.W, layout.D, layout.H, layout.h0
        self.tanb = self.H / self.D if self.H != 0.0 else 0.0
        self.tanb_q = _q(self.H) / _q(self.D) if self.H != 0.0 else Fraction(0)
        self.c = request["placement"]["minimum_clearance_m"]
        self.s = request["placement"]["structure_depth_m"]
        self.points = request["supports"]["points_ad_m"]
        self.t_slope = math.tan(math.radians(request["limits"]["max_ground_slope_deg"]))
        self.support_limit = request["limits"]["max_support_above_ground_m"]
        corners = np.array([t["footprint_xy_m"] for t in layout.tables], dtype=np.float64).reshape(-1, 2)
        if len(corners):
            region = (float(corners[:, 0].min()), float(corners[:, 1].min()), float(corners[:, 0].max()), float(corners[:, 1].max()))
        else:
            region = (0.0, 0.0, 1.0, 1.0)
        self.grid = _Grid(self.V, self.T, region)
        self.exact = _Exact()
        self.cand_total = 0
        self.cand_max = 0


# ---- the verifier --------------------------------------------------------------------------


_TABLE_ID = re.compile(r"T_j-?[0-9]+_i-?[0-9]+")
_MODULE_ID = re.compile(r"T_j-?[0-9]+_i-?[0-9]+_r[0-9]+_c[0-9]+")
_SUPPORT_ID = re.compile(r"S_T_j-?[0-9]+_i-?[0-9]+_[0-9]+")


def _num(x: Any) -> bool:
    return type(x) in (int, float)


def _points(x: Any, n: int, dim: int) -> bool:
    return isinstance(x, list) and len(x) == n and all(isinstance(p, list) and len(p) == dim and all(_num(c) for c in p) for p in x)


def _module_shape_ok(rec: Any) -> bool:
    return (
        isinstance(rec, dict)
        and set(rec) == {"seq", "module_id", "table_id", "corners_xyz_m"}
        and type(rec["seq"]) is int
        and rec["seq"] >= 0
        and isinstance(rec["module_id"], str)
        and _MODULE_ID.fullmatch(rec["module_id"]) is not None
        and isinstance(rec["table_id"], str)
        and _TABLE_ID.fullmatch(rec["table_id"]) is not None
        and _points(rec["corners_xyz_m"], 4, 3)
    )


def _support_shape_ok(rec: Any) -> bool:
    return (
        isinstance(rec, dict)
        and set(rec) == {"seq", "support_id", "table_id", "a_m", "d_m", "xy_m", "ground_z_m", "top_z_m", "above_ground_m"}
        and type(rec["seq"]) is int
        and rec["seq"] >= 0
        and isinstance(rec["support_id"], str)
        and _SUPPORT_ID.fullmatch(rec["support_id"]) is not None
        and isinstance(rec["table_id"], str)
        and _TABLE_ID.fullmatch(rec["table_id"]) is not None
        and _num(rec["a_m"])
        and rec["a_m"] >= 0
        and _num(rec["d_m"])
        and rec["d_m"] >= 0
        and _points([rec["xy_m"]], 1, 2)
        and all(_num(rec[k]) for k in ("ground_z_m", "top_z_m", "above_ground_m"))
    )


def _own_payload_digest(summary: dict[str, Any], tables, modules, supports) -> str:
    head = {k: summary.get(k) for k in ("schema_version", "placement_id", "source_layout", "terrain", "parameters_digest", "frame", "vertical", "z_kind", "policy", "counts")}
    h = hashlib.sha256(canonical_dumps(head).encode())
    for rec in [*tables, *modules, *supports]:
        h.update(("\n" + canonical_dumps(rec)).encode())
    return h.hexdigest()


def _norm(d: dict[str, Any] | None) -> dict[str, Any] | None:
    if d is None:
        return None
    out = dict(d)
    out.setdefault("crs", None)
    return out


def verify_placement(
    layout: Any,
    terrain: dict[str, Any],
    vertices: np.ndarray,
    triangles: np.ndarray,
    request: dict[str, Any],
    summary: dict[str, Any],
    tables: Iterable[dict[str, Any]],
    modules: Iterable[dict[str, Any]],
    supports: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Check a placement against its sources. `layout` carries the Module 01 summary fields
    and records (result_id, payload_digest, schema_version, algorithm_version, frame, u, v,
    W, D, H, h0, origin, tables, modules); `terrain` the stored terrain row."""
    tables, modules, supports = list(tables), list(modules), list(supports)
    ck = _Checks()
    ctx = _Ctx(layout, vertices, triangles, request)
    tol_z = policy.ELEVATION_TOL_M

    # schema and fixed contract fields ------------------------------------------------------
    for err in validator(RESULT).iter_errors(summary):
        ck.fail("schema", f"summary: {err.message}")
    v = validator(RESULT, "table_record")
    for rec in tables:
        for err in v.iter_errors(rec):
            ck.fail("schema", f"tables[{rec.get('seq')}]: {err.message}")
    # Module and support records are flat; they are checked against their $defs shapes by
    # direct code (equivalent and faster than a validator per record). The test suite also
    # runs the JSON Schema validator over every record.
    for rec in modules:
        if not _module_shape_ok(rec):
            ck.fail("schema", f"modules[{rec.get('seq') if isinstance(rec, dict) else '?'}]: does not match module_record")
    for rec in supports:
        if not _support_shape_ok(rec):
            ck.fail("schema", f"supports[{rec.get('seq') if isinstance(rec, dict) else '?'}]: does not match support_record")
    ck.require("contract_fields", summary.get("z_kind") == "terrain_vertical_reference", "z_kind is not terrain_vertical_reference")
    ck.require("contract_fields", summary.get("not_computed") == policy.NOT_COMPUTED, "not_computed is not the contract list")
    pol = summary.get("policy", {})
    expected_policy = {
        "policy": request["placement"]["policy"],
        "minimum_clearance_m": request["placement"]["minimum_clearance_m"],
        "structure_depth_m": request["placement"]["structure_depth_m"],
        "supports_model": request["supports"]["model"],
        "limits": request["limits"],
        "coverage": request["coverage"],
        "numerical_policy": POLICY_VERSION,
    }
    ck.require("contract_fields", pol == expected_policy, "policy block differs from the request parameters")
    for kind, recs in (("tables", tables), ("modules", modules), ("supports", supports)):
        ck.require("contract_fields", [r.get("seq") for r in recs] == list(range(len(recs))), f"{kind} seq is not 0..n-1 in order")

    # identity -------------------------------------------------------------------------------
    params = digest_of(
        {
            "placement": request["placement"],
            "supports": request["supports"],
            "limits": request["limits"],
            "coverage": request["coverage"],
            "expected_vertical": request.get("expected_vertical"),
        }
    )
    ck.require("identity", summary.get("parameters_digest") == params, "parameters_digest does not match the request")
    seed = "|".join([RESULT_SCHEMA, ALGORITHM_VERSION, POLICY_VERSION, layout.result_id, layout.payload_digest, terrain["terrain_digest"], params])
    pid = "plc_" + hashlib.sha256(seed.encode()).hexdigest()[:24]
    ck.require("identity", summary.get("placement_id") == pid, "placement_id does not follow from the sources and parameters")
    ck.require("identity", summary.get("terrain") == {"terrain_id": terrain["terrain_id"], "terrain_digest": terrain["terrain_digest"]}, "terrain identity differs from the stored terrain")

    # source linkage ---------------------------------------------------------------------------
    sl = summary.get("source_layout", {})
    ck.require(
        "source_linkage",
        sl == {"result_id": layout.result_id, "payload_digest": layout.payload_digest, "schema_version": layout.schema_version, "algorithm_version": layout.algorithm_version},
        "source_layout differs from the Module 01 result",
    )
    ck.require("source_linkage", len(tables) == len(layout.tables), f"{len(tables)} table records for {len(layout.tables)} Module 01 tables")
    for rec, rec01 in zip(tables, layout.tables):
        same = rec.get("table_id") == rec01["table_id"] and rec.get("footprint_xy_m") == rec01["footprint_xy_m"] and rec.get("module_count") == rec01["module_count"]
        ck.require("source_linkage", same, f"table {rec.get('table_id')}: id, footprint or module count differs from Module 01 record {rec01['table_id']}")

    # datum --------------------------------------------------------------------------------------
    ck.require("datum", _norm(summary.get("frame")) == _norm(terrain["frame"]), "summary frame differs from the terrain frame")
    ck.require("datum", _norm(terrain["frame"]) == _norm(layout.frame), "terrain frame differs from the layout frame")
    ck.require("datum", _norm(summary.get("vertical")) == _norm(terrain["vertical"]), "summary vertical reference differs from the terrain's")
    ev = request.get("expected_vertical")
    if ev is not None:
        tv = _norm(terrain["vertical"])
        ck.require("datum", ev["kind"] == tv["kind"] and ev.get("crs") == tv.get("crs") and ev.get("id") == tv.get("id"), "expected_vertical differs from the terrain's vertical reference")

    # per-table geometry ---------------------------------------------------------------------
    mods01: dict[str, list[dict[str, Any]]] = {}
    for m in layout.modules:
        mods01.setdefault(m["table_id"], []).append(m)
    mods_by_table: dict[str, list[dict[str, Any]]] = {}
    for m in modules:
        mods_by_table.setdefault(m.get("table_id"), []).append(m)
    sups_by_table: dict[str, list[dict[str, Any]]] = {}
    for s in supports:
        sups_by_table.setdefault(s.get("table_id"), []).append(s)
    expected_module_ids: list[str] = []
    expected_support_ids: list[str] = []
    capacity_w = 0.0
    status_n = {"placed": 0, "unknown_ground": 0, "infeasible": 0}
    for rec, rec01 in zip(tables, layout.tables):
        tid = rec01["table_id"]
        status = rec.get("status")
        status_n[status] = status_n.get(status, 0) + 1
        tb = _Table(ctx, rec01)
        tol_a = policy.AREA_REL_TOL * max(1.0, tb.footprint_area)
        covered = tb.covered_exactly()
        pieces, apart = tb.pieces()
        own_cov = sum(p[2] for p in pieces)
        cov, unc = rec.get("covered_area_m2", -1.0), rec.get("uncovered_area_m2", -1.0)
        ck.require("coverage", covered == (status != "unknown_ground"), f"{tid}: status {status} but the exact coverage test says {'covered' if covered else 'not covered'}")
        ck.require("coverage", _close(cov + unc, tb.footprint_area, tol_a), f"{tid}: covered + uncovered = {cov + unc} differs from the footprint area {tb.footprint_area}")
        ck.require("coverage", _close(cov, own_cov, tol_a) or (status == "unknown_ground" and own_cov <= tb.footprint_area and unc > 0 and cov <= own_cov + tol_a), f"{tid}: covered area {cov} differs from the clipped area {own_cov}")
        own_mods = [m["module_id"] for m in mods01.get(tid, [])]
        got_mods = mods_by_table.get(tid, [])
        got_sups = sups_by_table.get(tid, [])
        if status == "unknown_ground":
            ck.require("status_records", rec.get("reasons") == ["footprint_not_fully_covered"], f"{tid}: unknown_ground reasons {rec.get('reasons')}")
            ck.require("status_records", not any(k in rec for k in MEASURED), f"{tid}: unknown_ground table carries elevation fields")
            ck.require("status_records", unc > 0, f"{tid}: unknown_ground with no uncovered area")
            ck.require("status_records", not got_mods and not got_sups, f"{tid}: unknown_ground table has module or support records")
            continue
        missing = [k for k in MEASURED if k not in rec]
        if not ck.require("status_records", not missing, f"{tid}: {status} table lacks {missing}"):
            continue
        ck.require("status_records", unc == 0.0, f"{tid}: {status} table reports uncovered area {unc}")
        L = rec["lower_edge_z_m"]
        if not ck.require("coverage", bool(pieces), f"{tid}: {status} table has no surface under its footprint"):
            continue

        # elevations over the clipped pieces: plane value at every clipped vertex
        c0t = tb.Ft[0]
        pos = np.repeat(np.searchsorted(tb.cand, [t for t, _p, _a in pieces]), [len(poly) for _t, poly, _a in pieces])
        pts = np.concatenate([poly for _t, poly, _a in pieces])
        nrm, p0 = tb.normal[pos], tb.p0[pos]
        g = p0[:, 2] - (nrm[:, 0] * (pts[:, 0] - p0[:, 0]) + nrm[:, 1] * (pts[:, 1] - p0[:, 1])) / nrm[:, 2]
        dd = (pts - c0t) @ ctx.v
        w = g - dd * ctx.tanb
        own_L = float(w.max() + ctx.c + ctx.s)
        clear = L + dd * ctx.tanb - ctx.s - g
        ck.require("clearance", clear.min() >= ctx.c - tol_z, f"{tid}: clearance {clear.min()} below the minimum {ctx.c} at lower edge {L}")
        ck.require("lift_policy", _close(L, own_L, tol_z), f"{tid}: lower edge {L} is not the policy's minimum {own_L}")
        ck.require("elevations", _close(rec["upper_edge_z_m"], L + ctx.D * ctx.tanb, tol_z), f"{tid}: upper edge {rec['upper_edge_z_m']} != lower edge + D tan(beta)")
        ck.require("elevations", _close(rec["vertical_lift_m"], L - ctx.h0, tol_z), f"{tid}: vertical lift {rec['vertical_lift_m']} != lower edge - h0")
        ck.require("clearance_report", _close(rec["min_clearance_m"], clear.min(), tol_z), f"{tid}: min_clearance_m {rec['min_clearance_m']} but {clear.min()} recomputed")
        ck.require("clearance_report", _close(rec["max_clearance_m"], clear.max(), tol_z), f"{tid}: max_clearance_m {rec['max_clearance_m']} but {clear.max()} recomputed")
        at = rec["min_clearance_at_xy_m"]
        atq = (_q(at[0]), _q(at[1]))
        inside = all(_cross_q(tb.Fq[k], tb.Fq[(k + 1) % 4], atq) >= 0 for k in range(4))
        loc = tb.locate(atq, (at[0], at[1])) if inside else -1
        if ck.require("clearance_report", loc >= 0, f"{tid}: min_clearance_at_xy_m {at} is not on the covered footprint"):
            at_t = np.array(at) - ctx.origin
            c_at = L + float((at_t - c0t) @ ctx.v) * ctx.tanb - ctx.s - tb.ground(loc, at_t)
            ck.require("clearance_report", _close(c_at, rec["min_clearance_m"], tol_z), f"{tid}: clearance at min_clearance_at_xy_m is {c_at}, reported {rec['min_clearance_m']}")

        # slope: triangles whose interior meets the footprint interior, decided exactly
        piece_area = {t: a for t, _poly, a in pieces}
        slope_set = [(int(t), piece_area.get(int(t), 0.0)) for t, far in zip(tb.cand, apart) if not far and tb.interior_meets(int(t), piece_area.get(int(t), 0.0))]
        set_ids = np.array([t for t, _ in slope_set], dtype=np.int64)
        set_area = np.array([a for _, a in slope_set])
        exceeds = bool(tb.slope_exceeds_any(set_ids))
        nrm = tb.normal[np.searchsorted(tb.cand, set_ids)]
        gxy = -nrm[:, :2] / nrm[:, 2:3]
        gmax = float(np.hypot(gxy[:, 0], gxy[:, 1]).max())
        mean = (float((set_area * gxy[:, 0]).sum() / set_area.sum()), float((set_area * gxy[:, 1]).sum() / set_area.sum()))
        ck.require("slope", ("ground_slope_exceeds_limit" in rec["reasons"]) == exceeds, f"{tid}: slope reason {'missing' if exceeds else 'unexpected'}")
        ck.require("slope", _close(rec["max_ground_slope_deg"], math.degrees(math.atan(gmax)), policy.ANGLE_TOL_DEG), f"{tid}: max_ground_slope_deg {rec['max_ground_slope_deg']} but {math.degrees(math.atan(gmax))} recomputed")
        mu = (mean[0] * ctx.u[0] + mean[1] * ctx.u[1], mean[0] * ctx.v[0] + mean[1] * ctx.v[1])
        ck.require(
            "slope",
            _close(rec["mean_ground_gradient_uv"][0], mu[0], policy.GRADIENT_TOL) and _close(rec["mean_ground_gradient_uv"][1], mu[1], policy.GRADIENT_TOL),
            f"{tid}: mean_ground_gradient_uv {rec['mean_ground_gradient_uv']} but {list(mu)} recomputed",
        )

        # supports
        support_exceeds = False
        exact_L = None
        ids = [s.get("support_id") for s in got_sups]
        want = [f"S_{tid}_{k}" for k in range(len(ctx.points))]
        expected_support_ids.extend(want)
        ck.require("supports", ids == want, f"{tid}: support ids {ids[:3]}... differ from {want[:3]}...")
        for k, (sa, sd) in enumerate(ctx.points):
            s = got_sups[k] if k < len(got_sups) else None
            if s is None:
                continue
            pq = (
                tb.Fq[0][0] + _q(sa) / _q(ctx.W) * (tb.Fq[1][0] - tb.Fq[0][0]) + _q(sd) / _q(ctx.D) * (tb.Fq[3][0] - tb.Fq[0][0]),
                tb.Fq[0][1] + _q(sa) / _q(ctx.W) * (tb.Fq[1][1] - tb.Fq[0][1]) + _q(sd) / _q(ctx.D) * (tb.Fq[3][1] - tb.Fq[0][1]),
            )
            px = np.array([float(pq[0]), float(pq[1])])
            tri = tb.locate(pq, (px[0], px[1]))
            if not ck.require("supports", tri >= 0, f"{s.get('support_id')}: position is not on the surface"):
                continue
            ground = tb.ground(tri, px - ctx.origin)
            top = L + sd * ctx.tanb - ctx.s
            ck.require("supports", s.get("a_m") == sa and s.get("d_m") == sd, f"{s.get('support_id')}: (a, d) differs from the request")
            ck.require("supports", np.abs(np.array(s.get("xy_m")) - px).max() <= policy.PLAN_TOL_M, f"{s.get('support_id')}: xy {s.get('xy_m')} but {px.tolist()} recomputed")
            ck.require("supports", _close(s.get("ground_z_m"), ground, tol_z), f"{s.get('support_id')}: ground {s.get('ground_z_m')} but {ground} recomputed")
            ck.require("supports", _close(s.get("top_z_m"), top, tol_z), f"{s.get('support_id')}: top {s.get('top_z_m')} but {top} recomputed")
            ck.require("supports", _close(s.get("above_ground_m"), top - ground, tol_z), f"{s.get('support_id')}: above-ground {s.get('above_ground_m')} but {top - ground} recomputed")
            height = top - ground
            if abs(height - ctx.support_limit) <= policy.SUPPORT_LIMIT_BAND_M:
                if exact_L is None:
                    exact_L = tb.exact_lower_edge()
                support_exceeds |= exact_L + _q(sd) * ctx.tanb_q - _q(ctx.s) - tb.exact_ground(tri, pq) > _q(ctx.support_limit)
            else:
                support_exceeds |= height > ctx.support_limit
        ck.require("supports", ("support_above_ground_exceeds_limit" in rec["reasons"]) == support_exceeds, f"{tid}: support-height reason {'missing' if support_exceeds else 'unexpected'}")
        want_status = "infeasible" if (exceeds or support_exceeds) else "placed"
        ck.require("status_records", status == want_status, f"{tid}: status {status}, expected {want_status}")
        if status == "infeasible":
            ck.require("status_records", not got_mods, f"{tid}: infeasible table has module records")
            continue
        ck.require("status_records", rec["reasons"] == [], f"{tid}: placed table with reasons {rec['reasons']}")

        # module geometry
        delta = rec["vertical_lift_m"]
        ck.require("module_geometry", [m.get("module_id") for m in got_mods] == own_mods, f"{tid}: module ids differ from Module 01")
        expected_module_ids.extend(own_mods)
        for m, m01 in zip(got_mods, mods01.get(tid, [])):
            capacity_w += m01["power_wp"]
            cs = m.get("corners_xyz_m") or []
            ok = len(cs) == 4 and all(c[0] == c01[0] and c[1] == c01[1] and _close(c[2], c01[2] + delta, tol_z) for c, c01 in zip(cs, m01["corners_xyz_m"]))
            ck.require("module_geometry", ok, f"{m.get('module_id')}: corners are not the Module 01 corners raised by {delta}")

    ck.require("module_geometry", [m.get("module_id") for m in modules] == expected_module_ids, "module records are not exactly the placed tables' modules in Module 01 order")
    ck.require("supports", [s.get("support_id") for s in supports] == expected_support_ids, "support records are not exactly the measured tables' supports in order")

    # totals ---------------------------------------------------------------------------------
    counts = summary.get("counts", {})
    placed_tables = [r for r in tables if r.get("status") == "placed"]
    want_counts = {
        "tables": len(tables),
        "placed_tables": status_n.get("placed", 0),
        "unknown_ground_tables": status_n.get("unknown_ground", 0),
        "infeasible_tables": status_n.get("infeasible", 0),
        "placed_modules": sum(r.get("module_count", 0) for r in placed_tables),
        "supports": len(supports),
    }
    for k, val in want_counts.items():
        ck.require("totals", counts.get(k) == val, f"counts.{k} = {counts.get(k)}, records give {val}")
    ck.require("totals", counts.get("placed_modules") == len(modules), f"counts.placed_modules {counts.get('placed_modules')} != {len(modules)} module records")
    kwp = capacity_w / 1000.0
    ck.require("totals", _close(counts.get("placed_dc_capacity_kwp", -1), kwp, 1e-9 * max(1.0, kwp)), f"placed_dc_capacity_kwp {counts.get('placed_dc_capacity_kwp')} but {kwp} from the placed modules")
    ck.require("totals", counts.get("tables", 0) == counts.get("placed_tables", 0) + counts.get("unknown_ground_tables", 0) + counts.get("infeasible_tables", 0), "tables != placed + unknown_ground + infeasible")

    # payload --------------------------------------------------------------------------------
    ck.require("payload_integrity", _own_payload_digest(summary, tables, modules, supports) == summary.get("payload_digest"), "payload digest does not match the summary and records")

    ok = all(v["ok"] for v in ck.data.values())
    return {
        "ok": ok,
        "checks": ck.data,
        "candidates": {
            "method": "uniform grid over triangle bounding boxes",
            "grid_cell_m": ctx.grid.cell,
            "grid_cells": [ctx.grid.nx, ctx.grid.ny],
            "triangles_indexed": int(len(ctx.grid.ids)),
            "grid_assignments": ctx.grid.assignments,
            "candidate_triangles_total": int(ctx.cand_total),
            "candidate_triangles_max_per_table": int(ctx.cand_max),
        },
        "exact_rational_evaluations": ctx.exact.rational,
    }
