from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT.parent / "handoffs" / "module-01" / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def run_layout(req: dict, timeout_s: float | None = None):
    from solar_layout.layout import compute_layout
    from solar_layout.result import ResultRecords
    from solar_layout.validation import validate_layout_request

    val = validate_layout_request(req)
    comp = compute_layout(val, timeout_s=timeout_s)
    return val, comp, ResultRecords(comp)


def shifted(req: dict, dx: float, dy: float) -> dict:
    r = copy.deepcopy(req)

    def move(geom):
        if geom["type"] == "Polygon":
            geom["coordinates"] = [[[x + dx, y + dy] for x, y in ring] for ring in geom["coordinates"]]
        else:
            geom["coordinates"] = [[[[x + dx, y + dy] for x, y in ring] for ring in poly] for poly in geom["coordinates"]]

    move(r["boundary"])
    for e in r["exclusions"]:
        move(e["geometry"])
    ax, ay = r["placement"]["anchor_xy_m"]
    r["placement"]["anchor_xy_m"] = [ax + dx, ay + dy]
    return r


@pytest.fixture
def rectangle():
    return load_fixture("rectangle.request.json")


@pytest.fixture
def obstacle():
    return load_fixture("obstacle.request.json")
