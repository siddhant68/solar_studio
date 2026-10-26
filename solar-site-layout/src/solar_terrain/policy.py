"""Limits and the numerical policy terrain-policy/1 (CONTRACTS.md section 4).

Three kinds of comparison are kept apart:
* position and incidence (coverage, point location, overlaps, T-junctions): exact, no tolerance;
* areas: double-precision and informative, never used to decide a status;
* elevations: double precision, with an exact recomputation band at the support limit.
"""

from __future__ import annotations

import os
from fractions import Fraction

# ---- T1 limits (typed RESOURCE_LIMIT beyond them) -----------------------------------
MAX_VERTICES = 1_000_000
MAX_TRIANGLES = 2_000_000
MAX_ABS_XY_M = 10_000_000.0
MAX_ABS_Z_M = 20_000.0
MAX_SUPPORTS_PER_TABLE = 64
DEFAULT_TIMEOUT_S = 300.0


def timeout_s() -> float:
    """Wall-time limit for one terrain import or placement (SOLAR_TERRAIN_TIMEOUT_S)."""
    return float(os.environ.get("SOLAR_TERRAIN_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)))


# ---- terrain-policy/1 ----------------------------------------------------------------
# Decimal thresholds are compared as exact decimal rationals, never as their nearest double.
MIN_TRIANGLE_AREA_M2 = Fraction(1, 10**9)
T_JUNCTION_TOLERANCE_M = Fraction(1, 10**9)
# Support-height band: |height - limit| within this (double) triggers the exact recomputation.
SUPPORT_LIMIT_BAND_M = 1e-9
# Verifier agreement tolerances (comparisons, not decisions).
ELEVATION_TOL_M = 1e-9
PLAN_TOL_M = 1e-6
AREA_REL_TOL = 1e-9
ANGLE_TOL_DEG = 1e-9
GRADIENT_TOL = 1e-9

NOT_COMPUTED = ["embedment_depth", "pile_length", "foundation_design", "structural_adequacy", "grading", "cut_fill", "drainage"]

NUMERICAL_POLICY = {
    "version": "terrain-policy/1",
    "inputs": "decisions use the represented double values of the inputs (vertices, Module 01 footprint corners, W, D, H, a, d, c, s, limits); elevations are computed in the layout's anchor-translated frame",
    "incidence": "orientation, point-in-closed-triangle, segment-meets-open-polygon and interior-overlap decisions are exact (floating-point filter with a certified error bound, then exact expansion or rational arithmetic); there is no distance tolerance",
    "coverage": "boundary segments are triangle edges split at T-junction vertices that have no oppositely directed twin; a footprint is covered iff no boundary segment meets its open interior and its centroid lies in a triangle",
    "areas": "covered/uncovered areas are informative double sums of clipped triangle areas; never used to decide status",
    "elevations": "double precision; the support-height limit is decided exactly in rationals when |height - limit| <= 1e-9 m (equality is within the limit)",
    "slope": "a triangle exceeds the limit iff its squared gradient g^2 > t^2 exactly, t = math.tan(math.radians(limit)) in IEEE double; the reported angle degrees(atan(g)) is informative",
    "point_location": "lowest-index triangle whose closed area contains the point",
    "overlay": "footprint corners (point location), TIN vertices in the closed footprint (own z), proper crossings of triangle edges with footprint edges (interpolated along the triangle edge)",
    "min_clearance_tie_break": "largest G - d tan(beta); ties on equal doubles by smallest table-local d, then smallest a",
    "t_junction": "a vertex in the relative interior of another triangle's edge must match that edge's interpolated elevation within 1e-9 m, decided exactly",
    "minimum_triangle_area_m2": "1e-9, decided exactly",
    "unreferenced_vertices": "vertices used by no triangle are stored and part of the identity but take no part in the surface",
}

LIMITS = {
    "max_vertices": MAX_VERTICES,
    "max_triangles": MAX_TRIANGLES,
    "max_abs_xy_m": MAX_ABS_XY_M,
    "max_abs_z_m": MAX_ABS_Z_M,
    "max_supports_per_table": MAX_SUPPORTS_PER_TABLE,
    "timeout_s_default": DEFAULT_TIMEOUT_S,
}
