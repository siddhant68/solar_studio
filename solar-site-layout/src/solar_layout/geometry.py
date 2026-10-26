"""Table geometry conventions (START_HERE.md, "Table geometry").

Azimuth A is clockwise from frame north (N 0, E 90, S 180, W 270). In East/North
coordinates the unit table-width axis u and the uphill axis v are

    u = (-cos A,  sin A)
    v = (-sin A, -cos A)

so a south-facing table (A = 180) has u = East, v = North and rises towards North.
u x v = +1 for every A, so corners listed (a0,b0) (a1,b0) (a1,b1) (a0,b1) are
counter-clockwise in plan.

Exact cardinal azimuths use exact 0/+-1 components. That is an axis representation rule
only: input geometry is never moved.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_CARDINAL = {
    0.0: (0.0, 1.0),  # (sin A, cos A)
    90.0: (1.0, 0.0),
    180.0: (0.0, -1.0),
    270.0: (-1.0, 0.0),
}


def normalize_azimuth(azimuth_deg: float) -> float:
    a = math.fmod(float(azimuth_deg), 360.0)
    if a < 0.0:
        a += 360.0
    if a >= 360.0:  # -tiny + 360 can round up to 360
        a = 0.0
    return 0.0 if a == 0.0 else a


def sin_cos_azimuth(azimuth_deg: float) -> tuple[float, float]:
    a = normalize_azimuth(azimuth_deg)
    if a in _CARDINAL:
        return _CARDINAL[a]
    r = math.radians(a)
    return math.sin(r), math.cos(r)


def table_axes(azimuth_deg: float) -> tuple[tuple[float, float], tuple[float, float]]:
    s, c = sin_cos_azimuth(azimuth_deg)
    u = (-c + 0.0, s + 0.0)
    v = (-s + 0.0, -c + 0.0)
    return u, v


def sin_cos_tilt(tilt_deg: float) -> tuple[float, float]:
    if tilt_deg == 0.0:
        return 0.0, 1.0
    r = math.radians(tilt_deg)
    return math.sin(r), math.cos(r)


@dataclass(frozen=True)
class TableDims:
    module_w: float  # across the table (u), after orientation
    module_l: float  # up the slope (v), after orientation
    rows: int
    columns: int
    gap_x: float
    gap_y: float
    W: float  # table width along u
    L: float  # table slope length along v, in the table plane
    D: float  # horizontal projected depth L cos(beta)
    H: float  # total rise L sin(beta)
    sin_beta: float
    cos_beta: float
    lower_edge_height: float

    @property
    def modules_per_table(self) -> int:
        return self.rows * self.columns


def table_dims(module: dict, table: dict) -> TableDims:
    width = float(module["width_m"])
    length = float(module["length_m"])
    if module["orientation"] == "portrait":
        w, l = width, length
    else:
        w, l = length, width
    rows = int(table["rows"])
    cols = int(table["columns"])
    gx = float(table["module_gap_x_m"])
    gy = float(table["module_gap_y_m"])
    W = cols * w + (cols - 1) * gx
    L = rows * l + (rows - 1) * gy
    sb, cb = sin_cos_tilt(float(table["tilt_deg"]))
    return TableDims(
        module_w=w,
        module_l=l,
        rows=rows,
        columns=cols,
        gap_x=gx,
        gap_y=gy,
        W=W,
        L=L,
        D=L * cb,
        H=L * sb,
        sin_beta=sb,
        cos_beta=cb,
        lower_edge_height=float(table["lower_edge_height_m"]),
    )
