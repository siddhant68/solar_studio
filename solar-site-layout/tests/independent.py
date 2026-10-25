"""Independent expectation helpers for tests.

Nothing here imports the production generator: candidate counts for axis-aligned,
south-facing (A = 180) cases come from explicit interval arithmetic on the lattice.
"""

from __future__ import annotations

import math


def lattice_axis_positions(lo: float, hi: float, start: float, period: float, size: float) -> list[float]:
    """Origins start + k*period (k integer) with [o, o+size] inside [lo, hi]."""
    k_min = math.ceil((lo - start) / period - 1e-12)
    k_max = math.floor((hi - size - start) / period + 1e-12)
    return [start + k * period for k in range(k_min, k_max + 1)]


def rect_interior_overlap(a: tuple, b: tuple) -> bool:
    """Open-interior overlap of axis-aligned rectangles (x0, y0, x1, y1)."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def axis_aligned_expected_origins(
    site: tuple[float, float, float, float],
    setback: float,
    anchor: tuple[float, float],
    W: float,
    D: float,
    P: float,
    R: float,
    exclusions: list[tuple[float, float, float, float]] = (),
) -> list[tuple[float, float]]:
    """South-facing tables on a rectangular site, exclusions with zero keepout."""
    x0, y0, x1, y1 = site
    xs = lattice_axis_positions(x0 + setback, x1 - setback, anchor[0], P, W)
    ys = lattice_axis_positions(y0 + setback, y1 - setback, anchor[1], R, D)
    out = []
    for y in ys:
        for x in xs:
            fp = (x, y, x + W, y + D)
            if any(rect_interior_overlap(fp, e) for e in exclusions):
                continue
            out.append((x, y))
    return out
