"""Fixed-lattice table placement, bounded 3x3 phase search and layout quantities.

All geometry work happens in the computation frame: world coordinates translated by
the placement anchor (no rotation, no scaling). Candidate origins are

    o(i, j) = phase + i * (W + table_gap) * u + j * row_pitch * v

for integers i, j covering the site's extent along u and v. A candidate is kept only if
its complete footprint is covered by the site, keeps the perimeter setback from every
boundary ring and respects every exclusion keepout (see policy.GEOMETRY_POLICY).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
from shapely import STRtree

from . import ALGORITHM_VERSION, policy
from .errors import RESOURCE_LIMIT, DomainError
from .exact import distance_at_least, ring_segments
from .validation import Validated


@dataclass
class PhaseEval:
    p: int
    q: int
    offset_u_m: float
    offset_v_m: float
    candidates: int
    accepted_ij: np.ndarray  # (k, 2) int64: (i, j)
    accepted_corners: np.ndarray  # (k, 4, 2) local footprint corners
    rejected_counts: dict[str, int]
    rejection_records: list[dict[str, Any]]
    exact_checks: int

    @property
    def table_count(self) -> int:
        return int(self.accepted_ij.shape[0])


@dataclass
class LayoutComputation:
    validated: Validated
    P: float  # along-width lattice period W + table_gap
    R: float  # row pitch
    W_check: float  # footprint width actually checked (>= W, hull of module extents)
    L_check: float
    selected: PhaseEval
    phases: list[PhaseEval]
    table_origin_local: np.ndarray  # (k, 2)
    table_corners_local: np.ndarray  # (k, 4, 2)
    module_corners_local: np.ndarray  # (k, n_per, 4, 2)
    module_z: np.ndarray  # (n_per, 4) relative z for each module position in a table
    module_rc: np.ndarray  # (n_per, 2) (row, column)
    admissible_local: Any
    forbidden_local: Any
    quantities: dict[str, Any]
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _segments_of(geom) -> list:
    segs = []
    for ring in _rings(geom):
        segs.extend(ring_segments(list(ring.coords)))
    return segs


def _rings(geom):
    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    for p in polys:
        yield p.exterior
        yield from p.interiors


def _near_segments(segments_np: np.ndarray, segs_exact: list, quad: np.ndarray, reach: float) -> list:
    """Exact segments whose float bbox lies within `reach` of the quad's bbox."""
    qmin = quad.min(axis=0) - reach
    qmax = quad.max(axis=0) + reach
    smin = segments_np.min(axis=1)
    smax = segments_np.max(axis=1)
    mask = np.all(smax >= qmin, axis=1) & np.all(smin <= qmax, axis=1)
    return [segs_exact[i] for i in np.nonzero(mask)[0]]


class _Deadline:
    def __init__(self, seconds: float):
        self.seconds = seconds
        self.end = time.monotonic() + seconds

    def check(self, stage: str) -> None:
        if time.monotonic() > self.end:
            raise DomainError(
                RESOURCE_LIMIT,
                f"Layout generation exceeded its {self.seconds:g} s time limit during {stage}; nothing was saved",
                details={"limit": "generation_timeout_s", "value": self.seconds, "stage": stage},
            )


def lattice_bounds(val: Validated, offset_u: float, offset_v: float, P: float, R: float, W: float, D: float) -> tuple[int, int, int, int]:
    coords = shapely.get_coordinates(val.site_local)
    a = coords @ np.array(val.u)
    b = coords @ np.array(val.v)
    i_lo = math.floor((a.min() - W - offset_u) / P) - 1
    i_hi = math.ceil((a.max() - offset_u) / P) + 1
    j_lo = math.floor((b.min() - D - offset_v) / R) - 1
    j_hi = math.ceil((b.max() - offset_v) / R) + 1
    return i_lo, i_hi, j_lo, j_hi


def candidate_estimate(val: Validated) -> dict[str, Any]:
    dims = val.dims
    pl = val.normalized["placement"]
    P = dims.W + pl["table_gap_m"]
    R = pl["row_pitch_m"]
    i_lo, i_hi, j_lo, j_hi = lattice_bounds(val, 0.0, 0.0, P, R, dims.W, dims.D)
    per_phase = (i_hi - i_lo + 1) * (j_hi - j_lo + 1)
    phases = 9 if pl["mode"] == "phase_search_3x3" else 1
    return {
        "lattice_i_range": [i_lo, i_hi],
        "lattice_j_range": [j_lo, j_hi],
        "candidates_per_phase_upper_bound": per_phase,
        "phases": phases,
        "candidates_total_upper_bound": per_phase * phases,
        "max_modules_upper_bound": per_phase * dims.modules_per_table,
        "limits": {
            "max_candidates_per_phase": policy.MAX_CANDIDATES_PER_PHASE,
            "max_candidates_total": policy.MAX_CANDIDATES_TOTAL,
            "max_modules": policy.MAX_MODULES,
        },
    }


def _evaluate_phase(
    val: Validated,
    p: int,
    q: int,
    offset_u: float,
    offset_v: float,
    P: float,
    R: float,
    W: float,
    D: float,
    ctx: dict[str, Any],
    deadline: _Deadline,
) -> PhaseEval:
    u = np.array(val.u)
    v = np.array(val.v)
    i_lo, i_hi, j_lo, j_hi = lattice_bounds(val, offset_u, offset_v, P, R, W, D)
    ni, nj = i_hi - i_lo + 1, j_hi - j_lo + 1
    n = ni * nj
    if n > policy.MAX_CANDIDATES_PER_PHASE:
        raise DomainError(
            RESOURCE_LIMIT,
            f"{n} candidate table positions exceed the per-phase limit {policy.MAX_CANDIDATES_PER_PHASE}",
            details={"limit": "max_candidates_per_phase", "value": n},
        )
    I, J = np.meshgrid(np.arange(i_lo, i_hi + 1, dtype=np.int64), np.arange(j_lo, j_hi + 1, dtype=np.int64), indexing="xy")
    I = I.ravel()
    J = J.ravel()
    site = ctx["site"]
    setback = ctx["setback"]
    band = policy.DISTANCE_BAND_M
    accepted_mask = np.zeros(n, dtype=bool)
    corners_all = np.empty((n, 4, 2))
    rejected_counts: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    exact_checks = 0

    def reject(idx: np.ndarray, reason: str, chunk_I: np.ndarray, chunk_J: np.ndarray, record: bool):
        if idx.size == 0:
            return
        rejected_counts[reason] = rejected_counts.get(reason, 0) + int(idx.size)
        if record:
            for k in idx[: max(0, policy.MAX_REJECTION_RECORDS - len(records))]:
                records.append({"i": int(chunk_I[k]), "j": int(chunk_J[k]), "reason": reason})

    for start in range(0, n, policy.CANDIDATE_CHUNK):
        deadline.check(f"phase ({p},{q}) candidate evaluation")
        stop = min(n, start + policy.CANDIDATE_CHUNK)
        cI = I[start:stop]
        cJ = J[start:stop]
        a0 = cI * P + offset_u
        b0 = cJ * R + offset_v
        o = a0[:, None] * u[None, :] + b0[:, None] * v[None, :]
        c1 = o + W * u
        c2 = c1 + D * v
        c3 = o + D * v
        corners = np.stack([o, c1, c2, c3], axis=1)
        corners_all[start:stop] = corners
        rings = np.concatenate([corners, corners[:, :1, :]], axis=1)
        polys = shapely.polygons(rings)
        ok = shapely.covers(site, polys)
        touching = shapely.intersects(site, polys)
        reject(np.nonzero(~ok & touching)[0], "outside_site", cI, cJ, True)
        rejected_counts["outside_site_untouched"] = rejected_counts.get("outside_site_untouched", 0) + int(np.count_nonzero(~ok & ~touching))
        if setback > 0.0:
            idx = np.nonzero(ok)[0]
            if idx.size:
                too_close = shapely.dwithin(ctx["boundary"], polys[idx], setback - band)
                maybe = shapely.dwithin(ctx["boundary"], polys[idx], setback + band) & ~too_close
                bad = list(idx[too_close])
                for k in idx[maybe]:
                    exact_checks += 1
                    segs = _near_segments(ctx["boundary_np"], ctx["boundary_exact"], corners[k], setback + 1e-6)
                    if not distance_at_least(corners[k], segs, setback):
                        bad.append(k)
                bad = np.array(sorted(bad), dtype=np.int64)
                ok[bad] = False
                reject(bad, "perimeter_setback", cI, cJ, True)
        live = np.nonzero(ok)[0]
        if live.size and ctx["exclusions"]:
            tree = STRtree(polys[live])
            for ex_id, geom, keepout, ex_np, ex_exact in ctx["exclusions"]:
                if keepout == 0.0:
                    hits = tree.query(geom, predicate="intersects")
                    if hits.size == 0:
                        continue
                    cand = live[hits]
                    overlap = shapely.relate_pattern(geom, polys[cand], "T********")
                    bad = cand[overlap & ok[cand]]
                else:
                    hits = tree.query(geom, predicate="dwithin", distance=keepout + band)
                    if hits.size == 0:
                        continue
                    cand = live[hits]
                    cand = cand[ok[cand]]
                    too_close = shapely.dwithin(geom, polys[cand], keepout - band)
                    bad = list(cand[too_close])
                    for k in cand[~too_close]:
                        exact_checks += 1
                        segs = _near_segments(ex_np, ex_exact, corners[k], keepout + 1e-6)
                        if not distance_at_least(corners[k], segs, keepout):
                            bad.append(k)
                    bad = np.array(sorted(bad), dtype=np.int64)
                ok[bad] = False
                reject(bad, f"exclusion:{ex_id}", cI, cJ, True)
        accepted_mask[start:stop] = ok

    acc = np.nonzero(accepted_mask)[0]
    order = np.lexsort((I[acc], J[acc]))  # by j then i
    acc = acc[order]
    return PhaseEval(
        p=p,
        q=q,
        offset_u_m=offset_u,
        offset_v_m=offset_v,
        candidates=n,
        accepted_ij=np.stack([I[acc], J[acc]], axis=1) if acc.size else np.zeros((0, 2), dtype=np.int64),
        accepted_corners=corners_all[acc],
        rejected_counts=rejected_counts,
        rejection_records=records,
        exact_checks=exact_checks,
    )


def _segments_np(geom) -> np.ndarray:
    out = []
    for ring in _rings(geom):
        c = np.asarray(ring.coords)
        out.append(np.stack([c[:-1], c[1:]], axis=1))
    return np.concatenate(out, axis=0) if out else np.zeros((0, 2, 2))


def admissible_region(val: Validated, quad_segs: int = policy.ARC_QUAD_SEGMENTS, radius_factor: float = 1.0):
    s = val.normalized["perimeter_setback_m"]
    inner = val.site_local.buffer(-s * radius_factor, quad_segs=quad_segs) if s > 0 else val.site_local
    forb = [
        (g.buffer(k * radius_factor, quad_segs=quad_segs) if k > 0 else g) for _, g, k in val.exclusions_local
    ]
    forbidden = shapely.union_all(forb) if forb else shapely.Polygon()
    region = inner.difference(forbidden) if forb else inner
    return region, forbidden


def _ratio(num: float, den: float) -> float | None:
    return None if den == 0.0 else num / den


def compute_layout(val: Validated, timeout_s: float | None = None) -> LayoutComputation:
    deadline = _Deadline(policy.generation_timeout_s() if timeout_s is None else timeout_s)
    dims = val.dims
    pl = val.normalized["placement"]
    P = dims.W + pl["table_gap_m"]
    R = pl["row_pitch_m"]
    # Module extents along u and v, as the modules will actually be emitted.
    a_last_end = (dims.columns - 1) * (dims.module_w + dims.gap_x) + dims.module_w
    b_last_end = (dims.rows - 1) * (dims.module_l + dims.gap_y) + dims.module_l
    W_check = max(dims.W, a_last_end)
    L_check = max(dims.L, b_last_end)
    D_check = L_check * dims.cos_beta

    est = candidate_estimate(val)
    if est["candidates_total_upper_bound"] > policy.MAX_CANDIDATES_TOTAL:
        raise DomainError(
            RESOURCE_LIMIT,
            f"{est['candidates_total_upper_bound']} candidate table positions exceed the limit {policy.MAX_CANDIDATES_TOTAL}; nothing was computed",
            details={"limit": "max_candidates_total", "value": est["candidates_total_upper_bound"]},
        )
    if est["candidates_per_phase_upper_bound"] > policy.MAX_CANDIDATES_PER_PHASE:
        raise DomainError(
            RESOURCE_LIMIT,
            f"{est['candidates_per_phase_upper_bound']} candidate table positions exceed the per-phase limit {policy.MAX_CANDIDATES_PER_PHASE}; nothing was computed",
            details={"limit": "max_candidates_per_phase", "value": est["candidates_per_phase_upper_bound"]},
        )

    site = val.site_local
    shapely.prepare(site)
    boundary = shapely.boundary(site)
    shapely.prepare(boundary)
    exclusions = []
    for ex_id, g, k in val.exclusions_local:
        shapely.prepare(g)
        exclusions.append((ex_id, g, k, _segments_np(g), _segments_of(g)))
    ctx = {
        "site": site,
        "boundary": boundary,
        "boundary_np": _segments_np(site),
        "boundary_exact": _segments_of(site),
        "setback": val.normalized["perimeter_setback_m"],
        "exclusions": exclusions,
    }

    if pl["mode"] == "fixed_lattice":
        phase_list = [(0, 0)]
    else:
        phase_list = [(p, q) for p in range(3) for q in range(3)]
    phases = []
    for p, q in phase_list:
        off_u = 0.0 if p == 0 else p * P / 3.0
        off_v = 0.0 if q == 0 else q * R / 3.0
        phases.append(_evaluate_phase(val, p, q, off_u, off_v, P, R, W_check, D_check, ctx, deadline))
    # Highest module count; ties keep the earliest (p, q) in evaluation order, so phase
    # zero wins every tie it is part of.
    selected = phases[0]
    for ph in phases[1:]:
        if ph.table_count > selected.table_count:
            selected = ph

    k = selected.table_count
    n_per = dims.modules_per_table
    if k * n_per > policy.MAX_MODULES:
        raise DomainError(
            RESOURCE_LIMIT,
            f"The layout would place {k * n_per} modules, above the output limit {policy.MAX_MODULES}; nothing was saved",
            details={"limit": "max_modules", "value": k * n_per},
        )
    deadline.check("module generation")

    u = np.array(val.u)
    v = np.array(val.v)
    origins = selected.accepted_corners[:, 0, :] if k else np.zeros((0, 2))
    rr, cc = np.meshgrid(np.arange(dims.rows), np.arange(dims.columns), indexing="ij")
    rr = rr.ravel()
    cc = cc.ravel()
    A0 = cc * (dims.module_w + dims.gap_x)
    A1 = A0 + dims.module_w
    B0 = rr * (dims.module_l + dims.gap_y)
    B1 = B0 + dims.module_l
    A = np.stack([A0, A1, A1, A0], axis=1)  # (n_per, 4)
    B = np.stack([B0, B0, B1, B1], axis=1)
    Bh = B * dims.cos_beta
    offs = A[..., None] * u + Bh[..., None] * v  # (n_per, 4, 2)
    module_corners = origins[:, None, None, :] + offs[None, ...]  # (k, n_per, 4, 2)
    module_z = dims.lower_edge_height + B * dims.sin_beta

    region, forbidden = admissible_region(val)
    region_lo, _ = admissible_region(val, radius_factor=1.0 / math.cos(math.pi / (4 * policy.ARC_QUAD_SEGMENTS)))

    module_count = k * n_per
    width = val.normalized["module"]["width_m"]
    length = val.normalized["module"]["length_m"]
    power = val.normalized["module"]["power_wp"]
    physical = module_count * width * length
    projected = physical * dims.cos_beta
    footprint = k * dims.W * dims.D
    gross = float(site.area)
    polys = list(site.geoms) if site.geom_type == "MultiPolygon" else [site]
    outer_area = float(sum(shapely.Polygon(p.exterior).area for p in polys))
    buildable = float(region.area)
    quantities = {
        "table_count": k,
        "modules_per_table": n_per,
        "module_count": module_count,
        "module_power_wp": power,
        "dc_capacity_kwp": module_count * power / 1000.0,
        "physical_module_area_m2": physical,
        "projected_module_area_m2": projected,
        "table_footprint_area_m2": footprint,
        "gross_site_area_m2": gross,
        "outer_ring_area_m2": outer_area,
        "buildable_area_m2": buildable,
        "buildable_area_bounds_m2": [float(region_lo.area), buildable],
        "module_ground_coverage_gross": _ratio(projected, gross),
        "module_ground_coverage_buildable": _ratio(projected, buildable),
    }
    warnings = list(val.warnings)
    if k == 0:
        warnings.append(
            "No complete table fits the admissible region; the layout is empty (zero tables, zero modules, zero capacity)"
        )
    if buildable == 0.0:
        warnings.append("The admissible region is empty after setbacks and exclusions; buildable-area ratios are null")
    diagnostics = {
        "algorithm_version": ALGORITHM_VERSION,
        "candidates_evaluated": sum(ph.candidates for ph in phases),
        "exact_borderline_checks": sum(ph.exact_checks for ph in phases),
        "selected_phase_rejections": selected.rejected_counts,
        "rejection_records": selected.rejection_records,
        "rejection_records_truncated": sum(v for key, v in selected.rejected_counts.items() if key != "outside_site_untouched") > len(selected.rejection_records),
        "warnings": warnings,
        "W_check_m": W_check,
        "L_check_m": L_check,
    }
    return LayoutComputation(
        validated=val,
        P=P,
        R=R,
        W_check=W_check,
        L_check=L_check,
        selected=selected,
        phases=phases,
        table_origin_local=origins,
        table_corners_local=selected.accepted_corners,
        module_corners_local=module_corners,
        module_z=module_z,
        module_rc=np.stack([rr, cc], axis=1),
        admissible_local=region,
        forbidden_local=forbidden,
        quantities=quantities,
        diagnostics=diagnostics,
    )
