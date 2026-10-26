"""Validation and preparation of solar.terrain.surface/1 (CONTRACTS.md section 2).

Order of checks (each stage stops the import with typed errors before the next starts):
1. count limits (RESOURCE_LIMIT) before any per-element work;
2. the JSON Schema on the document, with the two large arrays checked separately by the
   same rules (INVALID_TERRAIN);
3. coordinate envelope (RESOURCE_LIMIT) and finite values;
4. triangle indices in range and distinct;
5. counter-clockwise triangles with plan area > 1e-9 m^2 (exact);
6. no two vertices with the same (x, y) (exact equality of doubles);
7. no two triangle interiors overlapping, and every T-junction crack-free (exact). Candidate
   pairs come from an STR-tree over triangle bounding boxes.

Preparation computes the coverage boundary used by the engine: directed triangle edges,
split at T-junction vertices, that have no oppositely directed twin.
"""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable

import numpy as np
import shapely

from solar_layout.errors import INVALID_TERRAIN, RESOURCE_LIMIT, DomainError, FieldError

from . import TERRAIN_SCHEMA, policy
from .predicates import ExactStats, exact_area2_exceeds, orient_sign
from .schemas import SURFACE, error_path, validator

MAX_FIELD_ERRORS = 20
_PAIR_CHUNK = 20_000  # triangles queried per STR-tree batch


@dataclass
class PreparedSurface:
    terrain_id: str
    terrain_digest: str
    name: str | None
    source: dict[str, Any]
    frame: dict[str, Any]
    vertical: dict[str, Any]
    vertices: np.ndarray  # (n, 3) float64, world coordinates
    triangles: np.ndarray  # (m, 3) int32, counter-clockwise
    boundary_segments: np.ndarray  # (k, 2) int32, directed (from, to) vertex indices
    info: dict[str, Any] = field(default_factory=dict)


def normalize_frame(frame: dict[str, Any]) -> dict[str, Any]:
    out = dict(frame)
    out.setdefault("crs", None)
    return out


def normalize_vertical(vertical: dict[str, Any]) -> dict[str, Any]:
    out = dict(vertical)
    out.setdefault("crs", None)
    return out


def _fail(errors: list[FieldError]) -> None:
    if errors:
        raise DomainError.from_field_errors(errors[:MAX_FIELD_ERRORS])


def _terr(fieldname: str, message: str, reason: str, **details: Any) -> FieldError:
    return FieldError(INVALID_TERRAIN, fieldname, message, {"reason": reason, **details})


# ---- identity -------------------------------------------------------------------------------


def _float_text(values: np.ndarray) -> list[str]:
    vals = np.where(values == 0.0, 0.0, values).tolist()
    return [float.__repr__(v) for v in vals]


def surface_digest(frame: dict[str, Any], vertical: dict[str, Any], vertices: np.ndarray, triangles: np.ndarray) -> tuple[str, str]:
    """terrain_digest and terrain_id. Streams exactly the bytes of Module 01's canonical
    JSON of {"frame", "triangles", "vertical", "vertices_xyz_m"} (sorted keys) into SHA-256,
    so a large surface is never held as one string."""
    from solar_layout.jsonio import canonical_dumps

    h = hashlib.sha256()
    h.update(b'{"frame":' + canonical_dumps(normalize_frame(frame)).encode() + b',"triangles":[')
    step = 200_000
    for i in range(0, len(triangles), step):
        chunk = triangles[i : i + step].tolist()
        text = ",".join(f"[{a},{b},{c}]" for a, b, c in chunk)
        h.update(((b"," if i else b"") + text.encode()))
    h.update(b'],"vertical":' + canonical_dumps(normalize_vertical(vertical)).encode() + b',"vertices_xyz_m":[')
    for i in range(0, len(vertices), step):
        chunk = vertices[i : i + step]
        xs, ys, zs = (_float_text(chunk[:, k]) for k in range(3))
        text = ",".join(f"[{x},{y},{z}]" for x, y, z in zip(xs, ys, zs))
        h.update(((b"," if i else b"") + text.encode()))
    h.update(b"]}")
    digest = h.hexdigest()
    return digest, "ter_" + hashlib.sha256((TERRAIN_SCHEMA + "|" + digest).encode()).hexdigest()[:24]


# ---- structural checks ----------------------------------------------------------------------


def _schema_check(doc: Any) -> None:
    if not isinstance(doc, dict):
        raise DomainError(INVALID_TERRAIN, "A terrain surface must be a JSON object", field="")
    envelope = dict(doc)
    if isinstance(envelope.get("vertices_xyz_m"), list):
        envelope["vertices_xyz_m"] = [[0.0, 0.0, 0.0]] * 3
    if isinstance(envelope.get("triangles"), list):
        envelope["triangles"] = [[0, 1, 2]]
    errors = []
    for err in sorted(validator(SURFACE).iter_errors(envelope), key=lambda e: (list(map(str, e.absolute_path)), e.message)):
        path = error_path(err)
        errors.append(_terr(path, f"{path or 'surface'}: {err.message}", "schema"))
    _fail(errors)


def _count_limits(doc: dict[str, Any]) -> None:
    verts, tris = doc.get("vertices_xyz_m"), doc.get("triangles")
    if isinstance(verts, list) and len(verts) > policy.MAX_VERTICES:
        raise DomainError(RESOURCE_LIMIT, f"{len(verts)} vertices exceed the limit of {policy.MAX_VERTICES}", field="vertices_xyz_m", details={"limit": "max_vertices", "value": len(verts), "max": policy.MAX_VERTICES})
    if isinstance(tris, list) and len(tris) > policy.MAX_TRIANGLES:
        raise DomainError(RESOURCE_LIMIT, f"{len(tris)} triangles exceed the limit of {policy.MAX_TRIANGLES}", field="triangles", details={"limit": "max_triangles", "value": len(tris), "max": policy.MAX_TRIANGLES})


def _rows_ok(rows: list, allowed: set[type]) -> bool:
    if set(map(type, rows)) != {list} or set(map(len, rows)) != {3}:
        return False
    return set(map(type, itertools.chain.from_iterable(rows))) <= allowed


def _vertices_array(rows: list) -> np.ndarray:
    if not _rows_ok(rows, {int, float}):
        for i, row in enumerate(rows):
            if type(row) is not list or len(row) != 3:
                raise DomainError.from_field_errors([_terr(f"vertices_xyz_m[{i}]", f"vertices_xyz_m[{i}]: must be [x, y, z]", "schema")])
            for k, v in enumerate(row):
                if type(v) not in (int, float):
                    raise DomainError.from_field_errors([_terr(f"vertices_xyz_m[{i}][{k}]", f"vertices_xyz_m[{i}][{k}]: must be a number", "schema")])
    try:
        arr = np.array(rows, dtype=np.float64)
    except OverflowError:
        arr = None
    if arr is None or not np.isfinite(arr).all():
        errors = []
        for i, row in enumerate(rows):
            for k, v in enumerate(row):
                try:
                    f = float(v)
                except OverflowError:
                    raise DomainError(RESOURCE_LIMIT, f"vertices_xyz_m[{i}][{k}] is beyond the coordinate envelope", field=f"vertices_xyz_m[{i}][{k}]", details={"limit": "max_abs_xy_m" if k < 2 else "max_abs_z_m"}) from None
                if not np.isfinite(f):
                    errors.append(_terr(f"vertices_xyz_m[{i}][{k}]", f"vertices_xyz_m[{i}][{k}]: non-finite number", "non_finite"))
        _fail(errors)
    return arr


def _envelope(vertices: np.ndarray) -> None:
    xy_bad = np.abs(vertices[:, :2]) > policy.MAX_ABS_XY_M
    z_bad = np.abs(vertices[:, 2]) > policy.MAX_ABS_Z_M
    if xy_bad.any() or z_bad.any():
        i, k = (np.argwhere(xy_bad)[0] if xy_bad.any() else (np.argwhere(z_bad)[0][0], 2))
        limit = "max_abs_xy_m" if k < 2 else "max_abs_z_m"
        bound = policy.MAX_ABS_XY_M if k < 2 else policy.MAX_ABS_Z_M
        raise DomainError(
            RESOURCE_LIMIT,
            f"vertices_xyz_m[{i}][{k}] = {vertices[i, k]!r} is beyond the supported envelope |value| <= {bound}",
            field=f"vertices_xyz_m[{i}][{k}]",
            details={"limit": limit, "max": bound, "value": float(vertices[i, k])},
        )


def _triangles_array(rows: list, n_vertices: int) -> np.ndarray:
    if not _rows_ok(rows, {int}):
        if not _rows_ok(rows, {int, float}):
            for i, row in enumerate(rows):
                if type(row) is not list or len(row) != 3:
                    raise DomainError.from_field_errors([_terr(f"triangles[{i}]", f"triangles[{i}]: must be three vertex indices", "schema")])
                for k, v in enumerate(row):
                    if type(v) not in (int, float):
                        raise DomainError.from_field_errors([_terr(f"triangles[{i}][{k}]", f"triangles[{i}][{k}]: must be an integer", "schema")])
        bad = [(i, k) for i, row in enumerate(rows) for k, v in enumerate(row) if type(v) is float and not (np.isfinite(v) and v == int(v))]
        if bad:
            i, k = bad[0]
            raise DomainError.from_field_errors([_terr(f"triangles[{i}][{k}]", f"triangles[{i}][{k}]: must be an integer", "schema")])
        rows = [[int(v) for v in row] for row in rows]
    errors = []
    try:
        arr = np.array(rows, dtype=np.int64)
    except OverflowError:
        arr = None
    if arr is None:
        for i, row in enumerate(rows):
            if any(v < 0 or v >= n_vertices for v in row):
                errors.append(_terr(f"triangles[{i}]", f"triangles[{i}]: vertex index out of range 0..{n_vertices - 1}", "index_out_of_range"))
        _fail(errors)
    bad = ((arr < 0) | (arr >= n_vertices)).any(axis=1)
    for i in np.nonzero(bad)[0][:MAX_FIELD_ERRORS]:
        errors.append(_terr(f"triangles[{i}]", f"triangles[{i}]: vertex index out of range 0..{n_vertices - 1}", "index_out_of_range"))
    _fail(errors)
    dup = (arr[:, 0] == arr[:, 1]) | (arr[:, 1] == arr[:, 2]) | (arr[:, 0] == arr[:, 2])
    for i in np.nonzero(dup)[0][:MAX_FIELD_ERRORS]:
        errors.append(_terr(f"triangles[{i}]", f"triangles[{i}]: repeats a vertex index (degenerate)", "degenerate"))
    _fail(errors)
    return arr.astype(np.int32)


# ---- geometric checks -----------------------------------------------------------------------


def _orientation(xy: np.ndarray, tris: np.ndarray, stats: ExactStats) -> None:
    t = xy[tris]  # (m, 3, 2)
    s = orient_sign(t[:, 0, 0], t[:, 0, 1], t[:, 1, 0], t[:, 1, 1], t[:, 2, 0], t[:, 2, 1], stats)
    errors = []
    for i in np.nonzero(s < 0)[0][:MAX_FIELD_ERRORS]:
        errors.append(_terr(f"triangles[{i}]", f"triangles[{i}]: clockwise in plan; triangles must be counter-clockwise", "clockwise"))
    for i in np.nonzero(s == 0)[0][: MAX_FIELD_ERRORS - len(errors)]:
        errors.append(_terr(f"triangles[{i}]", f"triangles[{i}]: zero plan area (collinear vertices)", "degenerate"))
    _fail(errors)
    big = exact_area2_exceeds(t, 2 * policy.MIN_TRIANGLE_AREA_M2, stats)
    for i in np.nonzero(~big)[0][:MAX_FIELD_ERRORS]:
        errors.append(_terr(f"triangles[{i}]", f"triangles[{i}]: plan area is not greater than 1e-9 m^2", "degenerate"))
    _fail(errors)


def _duplicates(xy: np.ndarray) -> None:
    order = np.lexsort((xy[:, 1], xy[:, 0]))
    s = xy[order]
    same = (s[1:, 0] == s[:-1, 0]) & (s[1:, 1] == s[:-1, 1])
    errors = []
    for k in np.nonzero(same)[0][:MAX_FIELD_ERRORS]:
        i, j = sorted((int(order[k]), int(order[k + 1])))
        errors.append(_terr(f"vertices_xyz_m[{j}]", f"vertices_xyz_m[{j}]: same plan position as vertices_xyz_m[{i}] (two elevations at one plan point)", "duplicate_plan_vertex", other=i))
    _fail(errors)


def _between(a: np.ndarray, b: np.ndarray, m: np.ndarray) -> np.ndarray:
    """For collinear a, b, m (all (P, 2)) with m distinct from a and b: m strictly between."""
    use_x = a[:, 0] != b[:, 0]
    lo_x, hi_x = np.minimum(a[:, 0], b[:, 0]), np.maximum(a[:, 0], b[:, 0])
    lo_y, hi_y = np.minimum(a[:, 1], b[:, 1]), np.maximum(a[:, 1], b[:, 1])
    in_x = (lo_x < m[:, 0]) & (m[:, 0] < hi_x)
    in_y = (lo_y < m[:, 1]) & (m[:, 1] < hi_y)
    return np.where(use_x, in_x, in_y)


def _pairs(xy: np.ndarray, tris: np.ndarray, stats: ExactStats, check: Callable[[str], None]) -> tuple[np.ndarray, int]:
    """Exact overlap check over STR-tree candidate pairs; returns the T-junctions as rows
    (triangle, edge, vertex) and the number of candidate pairs examined."""
    t = xy[tris]
    boxes = shapely.box(t[:, :, 0].min(axis=1), t[:, :, 1].min(axis=1), t[:, :, 0].max(axis=1), t[:, :, 1].max(axis=1))
    tree = shapely.STRtree(boxes)
    junctions = []
    errors: list[FieldError] = []
    n_pairs = 0
    for start in range(0, len(tris), _PAIR_CHUNK):
        q = tree.query(boxes[start : start + _PAIR_CHUNK])
        i = q[0] + start
        j = q[1]
        keep = i < j
        i, j = i[keep], j[keep]
        n_pairs += len(i)
        if len(i) == 0:
            continue
        ti, tj = t[i], t[j]
        vi, vj = tris[i], tris[j]
        separated = np.zeros(len(i), dtype=bool)
        for (ta, tb, va, vb, src) in ((ti, tj, vi, vj, i), (tj, ti, vj, vi, j)):
            # orientation of tb's vertices against each edge of ta: (P, 3 edges, 3 vertices)
            s = np.empty((len(i), 3, 3), dtype=np.int8)
            for e in range(3):
                a, b = ta[:, e, :], ta[:, (e + 1) % 3, :]
                s[:, e, :] = orient_sign(a[:, None, 0], a[:, None, 1], b[:, None, 0], b[:, None, 1], tb[:, :, 0], tb[:, :, 1], stats)
            separated |= (s <= 0).all(axis=2).any(axis=1)
            for e in range(3):
                ia, ib = va[:, e], va[:, (e + 1) % 3]
                for l in range(3):
                    m = vb[:, l]
                    cand = (s[:, e, l] == 0) & (m != ia) & (m != ib)
                    if not cand.any():
                        continue
                    k = np.nonzero(cand)[0]
                    inside = _between(ta[k, e, :], ta[k, (e + 1) % 3, :], tb[k, l, :])
                    k = k[inside]
                    if len(k):
                        junctions.append(np.stack([src[k], np.full(len(k), e), m[k]], axis=1))
        overlap = ~separated
        for k in np.nonzero(overlap)[0][: MAX_FIELD_ERRORS - len(errors)]:
            a, b = int(i[k]), int(j[k])
            errors.append(_terr(f"triangles[{b}]", f"triangles[{a}] and triangles[{b}] overlap in plan (a 2.5D surface maps each plan point to one elevation)", "overlap", other=a))
        if len(errors) >= MAX_FIELD_ERRORS:
            break
        check("surface overlap check")
    _fail(errors)
    if junctions:
        return np.unique(np.concatenate(junctions).astype(np.int64), axis=0), n_pairs
    return np.zeros((0, 3), dtype=np.int64), n_pairs


def _t_junction_z(vertices: np.ndarray, tris: np.ndarray, junctions: np.ndarray) -> None:
    errors = []
    tol = policy.T_JUNCTION_TOLERANCE_M
    for t, e, m in junctions.tolist():
        ia, ib = int(tris[t, e]), int(tris[t, (e + 1) % 3])
        a = [Fraction(float(c)) for c in vertices[ia]]
        b = [Fraction(float(c)) for c in vertices[ib]]
        p = [Fraction(float(c)) for c in vertices[m]]
        dx, dy = b[0] - a[0], b[1] - a[1]
        u = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
        z = a[2] + u * (b[2] - a[2])
        if abs(p[2] - z) > tol:
            errors.append(
                _terr(
                    f"vertices_xyz_m[{m}]",
                    f"vertices_xyz_m[{m}]: T-junction crack on edge ({ia}, {ib}) of triangles[{t}]: the vertex is {float(p[2] - z):+.6g} m from the edge's interpolated elevation (allowed 1e-9 m)",
                    "t_junction_crack",
                    triangle=int(t),
                    edge=[ia, ib],
                )
            )
            if len(errors) >= MAX_FIELD_ERRORS:
                break
    _fail(errors)


def boundary_segments(xy: np.ndarray, tris: np.ndarray, junctions: np.ndarray) -> np.ndarray:
    """Directed sub-edges (split at T-junction vertices) without an oppositely directed twin."""
    m = len(tris)
    starts = tris.reshape(-1).astype(np.int64)
    ends = np.roll(tris, -1, axis=1).reshape(-1).astype(np.int64)
    split_edges = set()
    sub_from: list[int] = []
    sub_to: list[int] = []
    if len(junctions):
        groups: dict[tuple[int, int], list[int]] = {}
        for t, e, v in junctions.tolist():
            groups.setdefault((t, e), []).append(v)
        for (t, e), vs in groups.items():
            a, b = int(tris[t, e]), int(tris[t, (e + 1) % 3])
            axis = 0 if xy[a, 0] != xy[b, 0] else 1
            sign = 1.0 if xy[b, axis] > xy[a, axis] else -1.0
            chain = [a] + sorted(vs, key=lambda v: sign * xy[v, axis]) + [b]
            sub_from.extend(chain[:-1])
            sub_to.extend(chain[1:])
            split_edges.add(3 * t + e)
    keep = np.ones(3 * m, dtype=bool)
    if split_edges:
        keep[np.fromiter(split_edges, dtype=np.int64)] = False
    f = np.concatenate([starts[keep], np.array(sub_from, dtype=np.int64)])
    g = np.concatenate([ends[keep], np.array(sub_to, dtype=np.int64)])
    n = int(max(f.max(initial=0), g.max(initial=0))) + 1
    keys = np.sort(f * n + g)
    rev = g * n + f
    pos = np.searchsorted(keys, rev)
    pos = np.minimum(pos, len(keys) - 1)
    twin = keys[pos] == rev
    seg = np.stack([f[~twin], g[~twin]], axis=1)
    order = np.lexsort((seg[:, 1], seg[:, 0]))
    return seg[order].astype(np.int32)


def validate_surface(doc: Any, check: Callable[[str], None] | None = None) -> PreparedSurface:
    check = check or (lambda stage: None)
    if isinstance(doc, dict):
        _count_limits(doc)
    _schema_check(doc)
    vertices = _vertices_array(doc["vertices_xyz_m"])
    _envelope(vertices)
    tris = _triangles_array(doc["triangles"], len(vertices))
    check("surface structure")
    stats = ExactStats()
    xy = np.ascontiguousarray(vertices[:, :2])
    _orientation(xy, tris, stats)
    _duplicates(xy)
    check("surface orientation")
    junctions, n_pairs = _pairs(xy, tris, stats, check)
    _t_junction_z(vertices, tris, junctions)
    check("surface T-junctions")
    segs = boundary_segments(xy, tris, junctions)
    digest, terrain_id = surface_digest(doc["frame"], doc["vertical"], vertices, tris)
    referenced = np.zeros(len(vertices), dtype=bool)
    referenced[tris.reshape(-1)] = True
    used = vertices[referenced]
    info = {
        "vertex_count": int(len(vertices)),
        "triangle_count": int(len(tris)),
        "referenced_vertex_count": int(referenced.sum()),
        "unreferenced_vertex_count": int((~referenced).sum()),
        "boundary_segment_count": int(len(segs)),
        "t_junction_count": int(len(junctions)),
        "overlap_candidate_pairs": int(n_pairs),
        "bbox_xy_m": [float(used[:, 0].min()), float(used[:, 1].min()), float(used[:, 0].max()), float(used[:, 1].max())],
        "z_range_m": [float(used[:, 2].min()), float(used[:, 2].max())],
        "exact_arithmetic": stats.as_dict(),
    }
    return PreparedSurface(
        terrain_id=terrain_id,
        terrain_digest=digest,
        name=doc.get("name"),
        source=doc.get("source") or {},
        frame=normalize_frame(doc["frame"]),
        vertical=normalize_vertical(doc["vertical"]),
        vertices=vertices,
        triangles=tris,
        boundary_segments=segs,
        info=info,
    )
