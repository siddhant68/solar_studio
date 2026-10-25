"""Helpers for tests that need separate OS processes (CLI, concurrent writers, crashes)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(data_dir: Path, *args: str, env: dict | None = None, check_json: bool = True, timeout: float = 300):
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.run(
        [sys.executable, "-m", "solar_layout.cli", "--data-dir", str(data_dir), *args],
        capture_output=True,
        text=True,
        env=e,
        timeout=timeout,
        cwd=str(ROOT),
    )
    out = json.loads(p.stdout) if (check_json and p.stdout.strip()) else None
    return p.returncode, out, p.stderr


def big_request(module_target: int = 10_000) -> dict:
    """A rectangular site sized for roughly `module_target` modules (2x14 tables)."""
    from conftest import load_fixture

    req = load_fixture("rectangle.request.json")
    req["name"] = f"Large site ~{module_target} modules"
    tables = module_target / 28
    # 2 x 14 tables: W = 14*1.134 + 13*0.02 = 16.136, P = 16.636; D = 2*2.278+0.02 cos(25)
    cols = int(tables**0.5 * 1.6) + 1
    rows = int(tables / cols) + 2
    width = cols * 16.636 + 10
    depth = rows * 6.5 + 10
    req["boundary"]["coordinates"] = [[[0, 0], [width, 0], [width, depth], [0, depth], [0, 0]]]
    req["perimeter_setback_m"] = 5.0
    req["module"] = {"model_id": "GENERIC-1134x2278-580", "width_m": 1.134, "length_m": 2.278, "power_wp": 580.0, "orientation": "portrait"}
    req["table"] = {"rows": 2, "columns": 14, "module_gap_x_m": 0.02, "module_gap_y_m": 0.02, "tilt_deg": 25.0, "facing_azimuth_deg": 180.0, "lower_edge_height_m": 0.8}
    req["placement"] = {"mode": "fixed_lattice", "anchor_xy_m": [5.0, 5.0], "table_gap_m": 0.5, "row_pitch_m": 6.5, "minimum_clear_row_gap_m": 1.5}
    return req
