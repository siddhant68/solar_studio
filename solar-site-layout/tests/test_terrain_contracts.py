"""TR03: the final contract package and the implementation agree.

Schemas are valid draft 2020-12 and packaged byte-identically; every fixture surface and
placement request validates; fixture regeneration is byte-identical; the independent
fixture checker passes; every terrain ID in surfaces/INDEX.json equals the implementation's.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

from solar_terrain.schemas import REQUEST, RESULT, SURFACE, load_schema
from solar_terrain.surface import validate_surface
from terrain_helpers import FX, ROOT, TERRAIN, load

CONTRACTS = TERRAIN / "contracts"
PACKAGED = ROOT / "src" / "solar_terrain" / "schemas"


@pytest.mark.parametrize("name", [SURFACE, REQUEST, RESULT])
def test_packaged_schemas_are_identical_and_valid(name):
    assert (PACKAGED / name).read_bytes() == (CONTRACTS / name).read_bytes()
    Draft202012Validator.check_schema(load_schema(name))


def test_fixture_surfaces_and_requests_validate():
    vs = Draft202012Validator(load_schema(SURFACE))
    vr = Draft202012Validator(load_schema(REQUEST))
    surfaces = sorted((FX / "surfaces").glob("*.surface.json"))
    assert len(surfaces) == 11
    for p in surfaces:
        assert not list(vs.iter_errors(json.loads(p.read_text()))), p.name
    n = 0
    for p in sorted((FX / "cases").glob("T*.json")):
        c = json.loads(p.read_text())
        if "placement_request" in c:
            assert not list(vr.iter_errors(c["placement_request"])), p.name
            n += 1
    assert n == 10


def test_terrain_ids_equal_the_fixture_index():
    index = load("surfaces/INDEX.json")
    assert len(index) == 11
    for name, ids in index.items():
        doc = load(f"surfaces/{name}.surface.json")
        if name == "hill-fan-tjunction-cracked":
            # identity is defined for any document; this one is rejected by validation (TC01)
            from solar_terrain.surface import surface_digest

            import numpy as np

            digest, tid = surface_digest(doc["frame"], doc["vertical"], np.array(doc["vertices_xyz_m"], dtype=float), np.array(doc["triangles"]))
        else:
            p = validate_surface(doc)
            digest, tid = p.terrain_digest, p.terrain_id
        assert (digest, tid) == (ids["terrain_digest"], ids["terrain_id"]), name


def test_identity_stream_equals_module01_canonical_json():
    """The streamed digest is the SHA-256 of Module 01's canonical JSON of the identity body."""
    from solar_layout.jsonio import canonical_dumps

    doc = load("surfaces/hill-fan-rotated.surface.json")
    body = {
        "frame": {**doc["frame"], "crs": doc["frame"].get("crs")},
        "vertical": {**doc["vertical"], "crs": doc["vertical"].get("crs")},
        "vertices_xyz_m": [[float(c) for c in v] for v in doc["vertices_xyz_m"]],
        "triangles": doc["triangles"],
    }
    assert validate_surface(doc).terrain_digest == hashlib.sha256(canonical_dumps(body).encode()).hexdigest()


def test_independent_fixture_checker_passes():
    p = subprocess.run([sys.executable, "-I", str(FX / "check_fixtures.py")], capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stdout + p.stderr
    assert p.stdout.strip().startswith("OK")


def test_fixture_regeneration_is_byte_identical(tmp_path):
    root = tmp_path / "handoffs"
    shutil.copytree(TERRAIN / "fixtures", root / "module-02-terrain" / "fixtures", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(TERRAIN.parent / "module-01" / "fixtures", root / "module-01" / "fixtures")
    copy = root / "module-02-terrain" / "fixtures"
    p = subprocess.run([sys.executable, "-I", str(copy / "make_fixtures.py")], capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stdout + p.stderr
    for orig in sorted(FX.glob("*/*.json")):
        assert (copy / orig.relative_to(FX)).read_bytes() == orig.read_bytes(), orig.name
