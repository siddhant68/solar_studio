"""Independent result verifier.

Separately implemented from the generator: it re-derives the axes and table dimensions
from the normalized request with its own formulas, and checks containment, setback,
exclusions and overlap with its own numpy geometry (vertex/segment distances, separating
axes, even-odd point-in-polygon) instead of GEOS predicates. Shapely is used here only
as a spatial index to find nearby pairs. Float decisions within the distance band are
re-decided with the exact rational kernel in `exact.py` (shared with the generator's
borderline path; that kernel has its own hand-checked tests).

It consumes records (summary, tables, modules) exactly as stored or exported, so it can
detect corrupted outputs as well as generator bugs. Besides geometry it checks every
record field the contract defines (IDs, lattice indices, heights, per-module power), that
record totals reconcile with the summary, the reported areas against its own area
computation, and the payload digest against the records it was given.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Iterable

import numpy as np
import shapely
from shapely import STRtree, box

from . import exact
from .jsonio import canonical_dumps
from .policy import ARC_QUAD_SEGMENTS, DISTANCE_BAND_M, VERIFY_COORDINATE_TOL_M

TABLE_FIELDS = frozenset({"seq", "table_id", "i", "j", "origin_xy_m", "footprint_xy_m", "lower_edge_z_m", "upper_edge_z_m", "module_count"})
MODULE_FIELDS = frozenset({"seq", "module_id", "table_id", "table_i", "table_j", "row", "column", "corners_xyz_m", "power_wp"})
PAYLOAD_SUMMARY_KEYS = ("schema_version", "input_digest", "computation_frame", "axes", "dimensions", "placement", "quantities")
# Buildable area is bracketed with arcs four times finer than the generator's
# polygonization; polygonization error falls as 1/q^2, so a correct reported bracket is
# at most ~16x as wide as this one (17x allowed).
AREA_CHECK_QUAD_SEGMENTS = 4 * ARC_QUAD_SEGMENTS
BRACKET_WIDTH_RATIO = 17.0

_CARD = {0.0: (0.0, 1.0), 90.0: (1.0, 0.0), 180.0: (0.0, -1.0), 270.0: (-1.0, 0.0)}


def _axes(az: float):
    a = az % 360.0
    s, c = _CARD.get(a, (math.sin(math.radians(a)), math.cos(math.radians(a))))
    return np.array([-c, s]) + 0.0, np.array([-s, -c]) + 0.0


def _dims(req: dict[str, Any]) -> dict[str, float]:
    m, t = req["module"], req["table"]
    w, l = (m["width_m"], m["length_m"]) if m["orientation"] == "portrait" else (m["length_m"], m["width_m"])
    W = t["columns"] * w + (t["columns"] - 1) * t["module_gap_x_m"]
    L = t["rows"] * l + (t["rows"] - 1) * t["module_gap_y_m"]
    beta = math.radians(t["tilt_deg"])
    cb = 1.0 if t["tilt_deg"] == 0 else math.cos(beta)
    sb = 0.0 if t["tilt_deg"] == 0 else math.sin(beta)
    return {"w": w, "l": l, "W": W, "L": L, "D": L * cb, "H": L * sb, "cb": cb, "sb": sb}


def _rings_of(geom: dict[str, Any]) -> list[np.ndarray]:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return [np.asarray(ring, dtype=float) for poly in polys for ring in poly]


def _point_in_rings(p: np.ndarray, rings: list[np.ndarray]) -> bool:
    """Even-odd ray casting over all rings (outer, holes, all components)."""
    inside = False
    x, y = p
    for ring in rings:
        xi, yi = ring[:-1, 0], ring[:-1, 1]
        xj, yj = ring[1:, 0], ring[1:, 1]
        cond = (yi > y) != (yj > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xcross = (xj - xi) * (y - yi) / (yj - yi) + xi
        crossings = np.count_nonzero(cond & (x < xcross))
        if crossings % 2:
            inside = not inside
    return inside


def _pt_seg_dist(P: np.ndarray, S: np.ndarray) -> np.ndarray:
    """Distances from points P (n,2) to segments S (m,2,2) -> (n,m)."""
    a = S[:, 0, :][None, :, :]
    b = S[:, 1, :][None, :, :]
    d = b - a
    len2 = np.sum(d * d, axis=2)
    pa = P[:, None, :] - a
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(len2 > 0, np.sum(pa * d, axis=2) / len2, 0.0)
    t = np.clip(t, 0.0, 1.0)
    c = a + t[..., None] * d
    return np.sqrt(np.sum((P[:, None, :] - c) ** 2, axis=2))


def _quad_edges(q: np.ndarray) -> np.ndarray:
    return np.stack([q, np.roll(q, -1, axis=0)], axis=1)


def _quad_boundary_distance(q: np.ndarray, S: np.ndarray) -> float:
    if S.shape[0] == 0:
        return math.inf
    d1 = _pt_seg_dist(q, S).min()
    d2 = _pt_seg_dist(S.reshape(-1, 2), _quad_edges(q)).min()
    return float(min(d1, d2))


def _seg_meets_open_quad(seg: np.ndarray, q: np.ndarray) -> bool | None:
    """Float separating-axis test; None when a sign is within the distance band."""
    a, b = seg
    for i in range(4):
        p, r = q[i], q[(i + 1) % 4]
        e = r - p
        n = math.hypot(*e)
        sa = (e[0] * (a[1] - p[1]) - e[1] * (a[0] - p[0])) / n
        sb = (e[0] * (b[1] - p[1]) - e[1] * (b[0] - p[0])) / n
        if (abs(sa) <= DISTANCE_BAND_M and sb <= DISTANCE_BAND_M) or (abs(sb) <= DISTANCE_BAND_M and sa <= DISTANCE_BAND_M):
            return None
        if sa < 0 and sb < 0:
            return False
    e = b - a
    n = math.hypot(*e)
    if n == 0:
        return None
    sides = (e[0] * (q[:, 1] - a[1]) - e[1] * (q[:, 0] - a[0])) / n
    if np.any(np.abs(sides) <= DISTANCE_BAND_M):
        return None
    return not (np.all(sides > 0) or np.all(sides < 0))


def _seg_meets_open_quad_decided(seg: np.ndarray, q: np.ndarray) -> bool:
    res = _seg_meets_open_quad(seg, q)
    if res is not None:
        return res
    return exact.segment_meets_open_convex((exact.fr(seg[0]), exact.fr(seg[1])), [exact.fr(p) for p in q])


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _ring_area(ring: np.ndarray) -> float:
    """Shoelace area of a closed ring, translated to its first vertex for conditioning."""
    r = ring - ring[0]
    x, y = r[:, 0], r[:, 1]
    return float(abs(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1])) / 2.0)


def _polys_of(geom: dict[str, Any]) -> list:
    return [geom["coordinates"]] if geom["type"] == "Polygon" else list(geom["coordinates"])


def _shapely_of(geom: dict[str, Any], shift: np.ndarray):
    polys = [shapely.Polygon(np.asarray(p[0], dtype=float) - shift, [np.asarray(h, dtype=float) - shift for h in p[1:]]) for p in _polys_of(geom)]
    return polys[0] if len(polys) == 1 else shapely.MultiPolygon(polys)


def _buildable_region(request: dict[str, Any], shift: np.ndarray, quad_segs: int, radius_factor: float):
    """Points of the site at least `setback` from every boundary ring and at least
    `keepout` from every exclusion, built as site minus buffered boundary LINES (the
    generator instead shrinks the site polygon with a negative buffer)."""
    site = _shapely_of(request["boundary"], shift)
    s = request["perimeter_setback_m"]
    region = site.difference(site.boundary.buffer(s * radius_factor, quad_segs=quad_segs)) if s > 0 else site
    for ex in request["exclusions"]:
        g = _shapely_of(ex["geometry"], shift)
        k = ex["keepout_m"]
        region = region.difference(g.union(g.boundary.buffer(k * radius_factor, quad_segs=quad_segs)) if k > 0 else g)
    return region


def payload_digest_of(summary: dict[str, Any], tables: Iterable[dict[str, Any]], modules: Iterable[dict[str, Any]]) -> str:
    """SHA-256 over the canonical numerical summary, then every table and module record."""
    h = hashlib.sha256()
    h.update(canonical_dumps({k: summary[k] for k in PAYLOAD_SUMMARY_KEYS}).encode())
    for rec in tables:
        h.update(b"\n")
        h.update(canonical_dumps(rec).encode())
    for rec in modules:
        h.update(b"\n")
        h.update(canonical_dumps(rec).encode())
    return h.hexdigest()


class _Report:
    def __init__(self):
        self.checks: dict[str, dict[str, Any]] = {}

    def add(self, name: str, ok: bool, detail: Any = None):
        entry = self.checks.setdefault(name, {"ok": True, "failures": 0, "examples": []})
        if not ok:
            entry["ok"] = False
            entry["failures"] += 1
            if len(entry["examples"]) < 5:
                entry["examples"].append(detail)

    def ensure(self, name: str):
        self.checks.setdefault(name, {"ok": True, "failures": 0, "examples": []})

    def result(self) -> dict[str, Any]:
        return {"ok": all(c["ok"] for c in self.checks.values()), "checks": self.checks}


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def verify_records(request: dict[str, Any], summary: dict[str, Any], tables: Iterable[dict[str, Any]], modules: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rep = _Report()
    for name in (
        "dimensions",
        "quantities",
        "identity_and_membership",
        "lattice_positions",
        "footprint_shape",
        "module_geometry",
        "module_within_table",
        "tables_disjoint",
        "site_containment",
        "perimeter_setback",
        "exclusions",
        "record_fields",
        "record_totals",
        "areas",
        "payload_integrity",
    ):
        rep.ensure(name)
    tol = VERIFY_COORDINATE_TOL_M
    dm = _dims(request)
    u, v = _axes(request["table"]["facing_azimuth_deg"])
    sd = summary["dimensions"]
    for key, mine in (("table_width_W_m", dm["W"]), ("table_slope_length_L_m", dm["L"]), ("table_projected_depth_D_m", dm["D"]), ("table_rise_H_m", dm["H"])):
        rep.add("dimensions", _close(sd[key], mine, 1e-9), {key: [sd[key], mine]})
    for k, mine in (("u_table_width_axis", u), ("v_uphill_axis", v)):
        rep.add("dimensions", np.allclose(summary["axes"][k], mine, atol=1e-12), {k: summary["axes"][k]})

    tables = list(tables)
    modules = list(modules)
    rows, cols = request["table"]["rows"], request["table"]["columns"]
    n_per = rows * cols
    q = summary["quantities"]
    power = request["module"]["power_wp"]
    rep.add("quantities", q["table_count"] == len(tables), {"table_count": [q["table_count"], len(tables)]})
    rep.add("quantities", q["module_count"] == len(modules) == len(tables) * n_per, {"module_count": [q["module_count"], len(modules), len(tables) * n_per]})
    rep.add("quantities", _close(q["dc_capacity_kwp"], len(modules) * power / 1000.0, 1e-9), {"dc_capacity_kwp": q["dc_capacity_kwp"]})
    phys = len(modules) * request["module"]["width_m"] * request["module"]["length_m"]
    rep.add("quantities", _close(q["physical_module_area_m2"], phys, 1e-9 * max(1.0, phys)), {"physical": q["physical_module_area_m2"]})
    rep.add("quantities", _close(q["projected_module_area_m2"], phys * dm["cb"], 1e-9 * max(1.0, phys)), {"projected": q["projected_module_area_m2"]})
    rep.add("quantities", _close(q["table_footprint_area_m2"], len(tables) * dm["W"] * dm["D"], 1e-9 * max(1.0, phys)), {"footprint": q["table_footprint_area_m2"]})
    for key, den in (("module_ground_coverage_gross", q["gross_site_area_m2"]), ("module_ground_coverage_buildable", q["buildable_area_m2"])):
        if den == 0:
            rep.add("quantities", q[key] is None, {key: "must be null for a zero denominator"})
        else:
            rep.add("quantities", q[key] is not None and _close(q[key], q["projected_module_area_m2"] / den, 1e-12), {key: q[key]})

    # record fields: every field the contract defines, per record
    h0 = request["table"]["lower_edge_height_m"]
    by_tid: dict[str, dict[str, Any]] = {}
    for k, t in enumerate(tables):
        ok = set(t) == TABLE_FIELDS
        ok = ok and t["seq"] == k and _is_int(t["i"]) and _is_int(t["j"]) and t["table_id"] == f"T_j{t['j']}_i{t['i']}"
        ok = ok and t["module_count"] == n_per and _is_int(t["module_count"])
        ok = ok and _close(t["lower_edge_z_m"], h0, tol) and _close(t["upper_edge_z_m"], h0 + dm["H"], tol)
        rep.add("record_fields", bool(ok), {"table_seq": k, "table_id": t.get("table_id")})
        if ok:
            by_tid[t["table_id"]] = t
    power_sum = 0.0
    for k, m in enumerate(modules):
        ok = set(m) == MODULE_FIELDS
        ok = ok and m["seq"] == k and all(_is_int(m[f]) for f in ("table_i", "table_j", "row", "column"))
        ok = ok and 0 <= m["row"] < rows and 0 <= m["column"] < cols
        ok = ok and m["table_id"] == f"T_j{m['table_j']}_i{m['table_i']}"
        ok = ok and m["module_id"] == f"{m['table_id']}_r{m['row']}_c{m['column']}"
        t = by_tid.get(m.get("table_id"))
        ok = ok and t is not None and (t["i"], t["j"]) == (m["table_i"], m["table_j"])
        ok = ok and m["power_wp"] == power and isinstance(m["power_wp"], (int, float)) and not isinstance(m["power_wp"], bool)
        rep.add("record_fields", bool(ok), {"module_seq": k, "module_id": m.get("module_id")})
        if isinstance(m.get("power_wp"), (int, float)) and not isinstance(m.get("power_wp"), bool):
            power_sum += float(m["power_wp"])

    # record totals reconcile with the summary
    rep.add("record_totals", q["module_power_wp"] == power, {"module_power_wp": [q["module_power_wp"], power]})
    rep.add("record_totals", q["modules_per_table"] == n_per, {"modules_per_table": [q["modules_per_table"], n_per]})
    table_modules = sum(t["module_count"] if _is_int(t.get("module_count")) else 0 for t in tables)
    rep.add("record_totals", table_modules == q["module_count"], {"sum_table_module_count": [table_modules, q["module_count"]]})
    rep.add(
        "record_totals",
        _close(power_sum / 1000.0, q["dc_capacity_kwp"], 1e-9 * max(1.0, abs(q["dc_capacity_kwp"]))),
        {"sum_module_power_kwp": power_sum / 1000.0, "summary_dc_capacity_kwp": q["dc_capacity_kwp"]},
    )

    # areas: gross and outer-ring areas by the shoelace formula; buildable area bracketed
    # independently with finer arcs (see _buildable_region)
    gross = outer = 0.0
    for poly in _polys_of(request["boundary"]):
        rings = [np.asarray(r, dtype=float) for r in poly]
        outer += _ring_area(rings[0])
        gross += _ring_area(rings[0]) - sum(_ring_area(r) for r in rings[1:])
    tol_a = 1e-9 * max(1.0, gross)
    rep.add("areas", _close(q["gross_site_area_m2"], gross, tol_a), {"gross_site_area_m2": [q["gross_site_area_m2"], gross]})
    rep.add("areas", _close(q["outer_ring_area_m2"], outer, tol_a), {"outer_ring_area_m2": [q["outer_ring_area_m2"], outer]})
    shift = np.array(request["placement"]["anchor_xy_m"], dtype=float)
    qs = AREA_CHECK_QUAD_SEGMENTS
    hi_i = float(_buildable_region(request, shift, qs, 1.0).area)
    lo_i = float(_buildable_region(request, shift, qs, 1.0 / math.cos(math.pi / (4 * qs))).area)
    lo_r, hi_r = q["buildable_area_bounds_m2"]
    b = q["buildable_area_m2"]
    rep.add("areas", _close(hi_r, b, tol_a) and lo_r <= b + tol_a and b <= gross + tol_a, {"buildable_area_m2": b, "bounds": [lo_r, hi_r]})
    rep.add("areas", lo_r <= hi_i + tol_a and lo_i <= hi_r + tol_a, {"reported_bounds": [lo_r, hi_r], "independent_bounds": [lo_i, hi_i]})
    rep.add("areas", hi_r - lo_r <= BRACKET_WIDTH_RATIO * (hi_i - lo_i) + tol_a, {"reported_bounds": [lo_r, hi_r], "independent_bounds": [lo_i, hi_i]})

    # payload digest over exactly these records
    try:
        digest = payload_digest_of(summary, tables, modules)
    except (KeyError, TypeError, ValueError) as e:
        digest = f"unhashable: {type(e).__name__}"
    rep.add("payload_integrity", summary.get("payload_digest") == digest, {"reported": summary.get("payload_digest"), "recomputed": digest})

    # identity and membership
    tid_set = set()
    ij_set = set()
    for t in tables:
        rep.add("identity_and_membership", t["table_id"] not in tid_set, {"duplicate_table_id": t["table_id"]})
        rep.add("identity_and_membership", (t["i"], t["j"]) not in ij_set, {"duplicate_lattice_index": [t["i"], t["j"]]})
        tid_set.add(t["table_id"])
        ij_set.add((t["i"], t["j"]))
    per_table: dict[str, set] = {}
    mid_set = set()
    for m in modules:
        rep.add("identity_and_membership", m["module_id"] not in mid_set, {"duplicate_module_id": m["module_id"]})
        mid_set.add(m["module_id"])
        rep.add("identity_and_membership", m["table_id"] in tid_set, {"orphan_module": m["module_id"]})
        per_table.setdefault(m["table_id"], set()).add((m["row"], m["column"]))
    full = {(r, c) for r in range(rows) for c in range(cols)}
    for t in tables:
        rep.add("identity_and_membership", per_table.get(t["table_id"], set()) == full, {"incomplete_table": t["table_id"]})

    # lattice positions and shapes, in the anchor-translated frame
    pl = summary["placement"]
    anchor = np.array(request["placement"]["anchor_xy_m"], dtype=float)
    P = dm["W"] + request["placement"]["table_gap_m"]
    R = request["placement"]["row_pitch_m"]
    off = pl["selected_offset_u_m"] * u + pl["selected_offset_v_m"] * v
    t_by_id = {}
    quads = []
    for t in tables:
        o_world = np.array(t["origin_xy_m"])
        expect = anchor + off + (t["i"] * P) * u + (t["j"] * R) * v
        rep.add("lattice_positions", np.allclose(o_world, expect, atol=tol, rtol=0), {"table": t["table_id"], "origin": t["origin_xy_m"], "expected": expect.tolist()})
        o = o_world - anchor
        fp = np.array(t["footprint_xy_m"]) - anchor
        shape = np.array([o, o + dm["W"] * u, o + dm["W"] * u + dm["D"] * v, o + dm["D"] * v])
        rep.add("footprint_shape", np.allclose(fp, shape, atol=tol, rtol=0), {"table": t["table_id"]})
        t_by_id[t["table_id"]] = (o, fp)
        quads.append(fp)
    gx, gy = request["table"]["module_gap_x_m"], request["table"]["module_gap_y_m"]
    for m in modules:
        if m["table_id"] not in t_by_id:
            continue
        o, fp = t_by_id[m["table_id"]]
        r, c = m["row"], m["column"]
        a0 = c * (dm["w"] + gx)
        b0 = r * (dm["l"] + gy)
        ab = [(a0, b0), (a0 + dm["w"], b0), (a0 + dm["w"], b0 + dm["l"]), (a0, b0 + dm["l"])]
        cxyz = np.array(m["corners_xyz_m"], dtype=float)
        exp_xy = np.array([o + a * u + (b * dm["cb"]) * v for a, b in ab])
        exp_z = np.array([h0 + b * dm["sb"] for _, b in ab])
        rep.add("module_geometry", np.allclose(cxyz[:, :2] - anchor, exp_xy, atol=tol, rtol=0) and np.allclose(cxyz[:, 2], exp_z, atol=tol, rtol=0), {"module": m["module_id"]})
        rel = cxyz[:, :2] - anchor - o
        aa = rel @ u
        bb = rel @ v
        inside = np.all(aa >= -tol) and np.all(aa <= dm["W"] + tol) and np.all(bb >= -tol) and np.all(bb <= dm["D"] + tol)
        rep.add("module_within_table", bool(inside), {"module": m["module_id"]})

    # pairwise table interiors disjoint
    if quads:
        Q = np.array(quads)
        tree = STRtree([box(*q.min(axis=0), *q.max(axis=0)) for q in Q])
        a_idx, b_idx = tree.query([box(*q.min(axis=0), *q.max(axis=0)) for q in Q], predicate="intersects")
        for ia, ib in zip(a_idx, b_idx):
            if ia >= ib:
                continue
            qa, qb = Q[ia], Q[ib]
            overlap = any(_seg_meets_open_quad_decided(e, qb) for e in _quad_edges(qa)) or any(
                _seg_meets_open_quad_decided(e, qa) for e in _quad_edges(qb)
            )
            same = np.allclose(qa, qb, atol=tol)
            rep.add("tables_disjoint", not (overlap or same), {"tables": [tables[ia]["table_id"], tables[ib]["table_id"]]})

    # site containment, setback and exclusions against the ORIGINAL geometry
    site_rings = [r - anchor for r in _rings_of(request["boundary"])]
    site_segs = np.concatenate([np.stack([r[:-1], r[1:]], axis=1) for r in site_rings])
    seg_tree = STRtree([box(*s.min(axis=0), *s.max(axis=0)) for s in site_segs])
    setback = request["perimeter_setback_m"]
    exclusions = []
    for ex in request["exclusions"]:
        rings = [r - anchor for r in _rings_of(ex["geometry"])]
        segs = np.concatenate([np.stack([r[:-1], r[1:]], axis=1) for r in rings])
        exclusions.append((ex["id"], rings, segs, STRtree([box(*s.min(axis=0), *s.max(axis=0)) for s in segs]), ex["keepout_m"]))
    for t, fp in zip(tables, quads):
        centre = fp.mean(axis=0)
        lo, hi = fp.min(axis=0), fp.max(axis=0)
        near = seg_tree.query(box(*(lo - setback - 1e-6), *(hi + setback + 1e-6)))
        crossing = any(_seg_meets_open_quad_decided(site_segs[k], fp) for k in near)
        inside = _point_in_rings(centre, site_rings)
        rep.add("site_containment", inside and not crossing, {"table": t["table_id"], "centre_inside": inside, "boundary_crossing": crossing})
        if setback > 0 and near.size:
            d = _quad_boundary_distance(fp, site_segs[near])
            if abs(d - setback) <= DISTANCE_BAND_M:
                ok = exact.distance_at_least(fp.tolist(), [(exact.fr(s[0]), exact.fr(s[1])) for s in site_segs[near]], setback)
            else:
                ok = d > setback
            rep.add("perimeter_setback", ok, {"table": t["table_id"], "distance_m": d, "required_m": setback})
        for ex_id, rings, segs, tree, keepout in exclusions:
            near_e = tree.query(box(*(lo - keepout - 1e-6), *(hi + keepout + 1e-6)))
            if near_e.size == 0 and not _point_in_rings(centre, rings):
                continue
            meets = any(_seg_meets_open_quad_decided(segs[k], fp) for k in near_e)
            within = _point_in_rings(centre, rings)
            ok = not meets and not within
            if ok and keepout > 0 and near_e.size:
                d = _quad_boundary_distance(fp, segs[near_e])
                if abs(d - keepout) <= DISTANCE_BAND_M:
                    ok = exact.distance_at_least(fp.tolist(), [(exact.fr(s[0]), exact.fr(s[1])) for s in segs[near_e]], keepout)
                else:
                    ok = d > keepout
            rep.add("exclusions", ok, {"table": t["table_id"], "exclusion": ex_id})
    return rep.result()
