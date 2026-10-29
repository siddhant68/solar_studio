"""Shared helpers for the Module 02 terrain tests (fixtures in handoffs/module-02-terrain)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT.parent / "handoffs" / "module-02-terrain"
FX = TERRAIN / "fixtures"
NUMERIC_CASES = ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T11", "T12", "T13"]


def load(rel: str | Path) -> Any:
    return json.loads((FX / rel).read_text())


def case(case_id: str) -> dict:
    return load(f"cases/{case_id}.json")


def layout_request(c: dict) -> dict:
    """Layout request paths in case files are relative to the fixtures directory."""
    return json.loads((FX / c["layout"]["request"]).resolve().read_text())


def surface(c: dict) -> dict:
    """Surface paths in case files are relative to the cases directory."""
    return json.loads((FX / "cases" / c["surface"]).resolve().read_text())


def services(data_dir: Path):
    from solar_layout.service import SolarService
    from solar_terrain.service import TerrainService

    svc = SolarService(data_dir)
    return svc, TerrainService(svc, data_dir)


def prepare(ts, svc, c: dict) -> dict:
    """Generate the case's layout and import its surface; return the placement request."""
    lay = svc.generate_layout(request=layout_request(c))
    assert lay["result_id"] == c["placement_request"]["source_layout"]["result_id"]
    ter = ts.import_terrain(surface(c))
    assert ter["terrain_id"] == c["placement_request"]["terrain"]
    return copy.deepcopy(c["placement_request"])


def place_case(ts, svc, case_id: str) -> tuple[dict, dict]:
    c = case(case_id)
    out = ts.place_on_terrain(prepare(ts, svc, c))
    return c, out


def all_items(ts, pid: str, kind: str) -> list[dict]:
    items, cursor = [], None
    while True:
        page = ts.get_placement_items(pid, kind, cursor=cursor, limit=500)
        items += page["items"]
        cursor = page["next_cursor"]
        if cursor is None:
            return items


def grid_surface(frame: dict, lo, hi, n: int, z=lambda x, y: 100.0 + 0.02 * x + 0.03 * y, vertical: dict | None = None) -> dict:
    """Regular n x n vertex grid over [lo, hi], two counter-clockwise triangles per cell."""
    xs = np.linspace(lo[0], hi[0], n)
    ys = np.linspace(lo[1], hi[1], n)
    X, Y = np.meshgrid(xs, ys)
    Z = z(X - lo[0], Y - lo[1])
    V = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    i, j = np.meshgrid(np.arange(n - 1), np.arange(n - 1))
    a = (j * n + i).ravel()
    T = np.concatenate([np.stack([a, a + 1, a + n + 1], 1), np.stack([a, a + n + 1, a + n], 1)])
    return {
        "schema_version": "solar.terrain.surface/1",
        "name": f"grid {n}x{n}",
        "frame": frame,
        "vertical": vertical or {"kind": "local", "id": "local:test-grid", "units": "m", "positive": "up"},
        "vertices_xyz_m": V.tolist(),
        "triangles": T.tolist(),
    }
