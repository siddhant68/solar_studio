"""Declared supported envelope, resource limits and numerical policy (geom-policy/1).

Distance, area and serialization tolerances are separate on purpose; none of them is a
positive buffer applied to the site.
"""

from __future__ import annotations

import os

# ---- Supported envelope (typed RESOURCE_LIMIT beyond it) --------------------------------
MAX_ABS_COORDINATE_M = 10_000_000.0
MAX_SITE_DIAGONAL_M = 20_000.0
MIN_MODULE_DIMENSION_M = 0.05
MAX_MODULE_DIMENSION_M = 10.0
# The anchor is the world origin of the computation frame; it must lie near the site so
# that local coordinates stay well conditioned.
MAX_ANCHOR_DISTANCE_FROM_SITE_BBOX_M = 20_000.0
MAX_BOUNDARY_VERTICES = 100_000
MAX_EXCLUSION_VERTICES_TOTAL = 100_000

# ---- Work and output limits ----------------------------------------------------------
MAX_CANDIDATES_PER_PHASE = 400_000
MAX_CANDIDATES_TOTAL = 1_200_000  # all phases of one generation
MAX_MODULES = 60_000
MAX_REJECTION_RECORDS = 2_000  # per-candidate rejection reasons kept in a result
CANDIDATE_CHUNK = 20_000  # deadline checked between chunks


def generation_timeout_s() -> float:
    return float(os.environ.get("SOLAR_LAYOUT_TIMEOUT_S", "60"))


# ---- Numerical policy ------------------------------------------------------------------
# Distance band: a float distance margin |d - required| below this is "borderline" and is
# decided by exact rational arithmetic on the float coordinates as represented.
DISTANCE_BAND_M = 1e-9
# Row pitch: the clear-gap requirement allows this much rounding in D = L cos(beta).
# Physical overlap (row_pitch < D) has no tolerance.
PITCH_TOLERANCE_M = 1e-9
# Admissible-region polygonization: segments per quarter circle for setback/keepout arcs.
ARC_QUAD_SEGMENTS = 64
# Test/verification comparison tolerances (not used to decide placements).
VERIFY_COORDINATE_TOL_M = 1e-6
AREA_REL_TOL = 1e-12
# Row-pitch calculator.
MIN_SOLAR_ELEVATION_DEG = 1.0  # tilted tables; below this the estimate is refused

GEOMETRY_POLICY = {
    "version": "geom-policy/1",
    "computation_frame": "world coordinates translated by the placement anchor (x_local = x_world - anchor_x); no rotation or scaling of the site",
    "containment": "a complete table footprint must be covered by the site polygon (GEOS covers, exact predicate); tangency to the boundary is allowed",
    "setback": "minimum Euclidean distance from the footprint to every site boundary ring (outer and holes, all components) must be >= perimeter_setback_m",
    "exclusion_keepout_zero": "footprint and exclusion interiors must be disjoint (GEOS relate, exact predicate); touching is allowed",
    "exclusion_keepout_positive": "minimum Euclidean distance from the footprint to the exclusion polygon must be >= keepout_m",
    "borderline": f"float distance margins within {DISTANCE_BAND_M} m of the requirement are re-decided exactly with rational arithmetic on the represented coordinates",
    "partial_tables": "never; an inadmissible table is dropped whole",
    "admissible_region_display": f"site.buffer(-setback) minus union(exclusion.buffer(keepout)), round joins, {ARC_QUAD_SEGMENTS} segments per quarter circle; used for display and buildable area only, never for placement decisions",
    "buildable_area_bounds": "lower bound uses arc radius r/cos(pi/(4*q)) (polygon outside the true arc), upper bound uses chords on the true arc",
    "pitch_tolerance_m": PITCH_TOLERANCE_M,
    "serialization": "shortest round-trip decimal (Python repr) for every float; -0.0 written as 0.0",
}

LIMITS = {
    "max_abs_coordinate_m": MAX_ABS_COORDINATE_M,
    "max_site_diagonal_m": MAX_SITE_DIAGONAL_M,
    "min_module_dimension_m": MIN_MODULE_DIMENSION_M,
    "max_module_dimension_m": MAX_MODULE_DIMENSION_M,
    "max_anchor_distance_from_site_bbox_m": MAX_ANCHOR_DISTANCE_FROM_SITE_BBOX_M,
    "max_boundary_vertices": MAX_BOUNDARY_VERTICES,
    "max_exclusion_vertices_total": MAX_EXCLUSION_VERTICES_TOTAL,
    "max_candidates_per_phase": MAX_CANDIDATES_PER_PHASE,
    "max_candidates_total": MAX_CANDIDATES_TOTAL,
    "max_modules": MAX_MODULES,
    "generation_timeout_s_default": 60.0,
}
