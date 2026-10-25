"""CSV export: one row per module.

Column order is fixed (CSV_COLUMNS). Corners c0..c3 follow the module's own order:
c0 lower edge at a0, c1 lower edge at a1, c2 upper edge at a1, c3 upper edge at a0
(a along the table-width axis u, "lower" = facing side); counter-clockwise in plan.
x/y are world-frame metres in the request's frame; z is relative to the layout's flat
datum (z_kind relative_flat_datum). Numbers use the shortest round-trip decimal form.
"""

from __future__ import annotations

import csv
import io
from typing import IO, Iterable

from ..jsonio import fmt_float

CSV_COLUMNS = [
    "module_id",
    "table_id",
    "table_i",
    "table_j",
    "module_row",
    "module_column",
    "c0_x_m", "c0_y_m", "c0_z_rel_m",
    "c1_x_m", "c1_y_m", "c1_z_rel_m",
    "c2_x_m", "c2_y_m", "c2_z_rel_m",
    "c3_x_m", "c3_y_m", "c3_z_rel_m",
    "power_wp",
]


def write_csv(out: IO[str], modules: Iterable[dict]) -> None:
    w = csv.writer(out, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for m in modules:
        row = [m["module_id"], m["table_id"], m["table_i"], m["table_j"], m["row"], m["column"]]
        for x, y, z in m["corners_xyz_m"]:
            row.extend([fmt_float(x), fmt_float(y), fmt_float(z)])
        row.append(fmt_float(m["power_wp"]))
        w.writerow(row)


def csv_text(modules: Iterable[dict]) -> str:
    buf = io.StringIO()
    write_csv(buf, modules)
    return buf.getvalue()
