"""Validate this planning package and rewrite PACKAGE_VALIDATION.json and SHA256SUMS.json.

    ../../solar-site-layout/.venv/bin/python validate_package.py

Checks: the three schemas are valid draft 2020-12; every fixture surface validates and
every placement request validates; regenerating the fixtures is byte-identical; the
independent checker passes. Needs jsonschema (in the Module 01 environment).
"""

from __future__ import annotations

import glob
import hashlib
import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent


def tree_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((HERE / "fixtures").glob("*/*.json")):
        h.update(f"{p.relative_to(HERE)} {hashlib.sha256(p.read_bytes()).hexdigest()}\n".encode())
    return h.hexdigest()


def main() -> int:
    schemas = {n: json.loads((HERE / "contracts" / f"{n}.schema.json").read_text()) for n in ("terrain-surface", "placement-request", "placement-result")}
    for s in schemas.values():
        Draft202012Validator.check_schema(s)
    vs, vr = Draft202012Validator(schemas["terrain-surface"]), Draft202012Validator(schemas["placement-request"])
    surfaces = {Path(f).name: [e.message for e in vs.iter_errors(json.loads(Path(f).read_text()))] for f in sorted(glob.glob(str(HERE / "fixtures/surfaces/*.surface.json")))}
    requests = {}
    for f in sorted(glob.glob(str(HERE / "fixtures/cases/*.json"))):
        c = json.loads(Path(f).read_text())
        if "placement_request" in c:
            requests[Path(f).name] = [e.message for e in vr.iter_errors(c["placement_request"])]
    before = tree_hash()
    gen = subprocess.run([sys.executable, "-I", str(HERE / "fixtures/make_fixtures.py")], capture_output=True, text=True)
    after = tree_hash()
    chk = subprocess.run([sys.executable, "-I", str(HERE / "fixtures/check_fixtures.py")], capture_output=True, text=True)
    out = {
        "scope": "checks of the Module 02 contract package (schemas and fixtures); implementation evidence is in solar-site-layout/reports/TERRAIN_ACCEPTANCE.json",
        "checks": {
            "schemas_valid_draft_2020_12": True,
            "surfaces_validate": {"passed": not any(surfaces.values()), "errors": {k: v for k, v in surfaces.items() if v}, "count": len(surfaces)},
            "placement_requests_validate": {"passed": not any(requests.values()), "errors": {k: v for k, v in requests.items() if v}, "count": len(requests)},
            "fixture_regeneration_byte_identical": {"passed": gen.returncode == 0 and before == after, "tree_sha256": after},
            "independent_fixture_checker": {"passed": chk.returncode == 0, "output": chk.stdout.strip() or chk.stderr.strip()},
        },
        "tools": {"python": sys.version.split()[0], "jsonschema": version("jsonschema")},
    }
    out["passed"] = all(v if isinstance(v, bool) else v["passed"] for v in out["checks"].values())
    (HERE / "PACKAGE_VALIDATION.json").write_text(json.dumps(out, indent=1) + "\n")
    files = sorted(p for p in HERE.rglob("*") if p.is_file() and p.name != "SHA256SUMS.json" and "__pycache__" not in p.parts)
    (HERE / "SHA256SUMS.json").write_text(json.dumps({"algorithm": "sha256", "files": {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}, indent=1) + "\n")
    print(json.dumps({k: (v if isinstance(v, bool) else v["passed"]) for k, v in out["checks"].items()}), "files hashed:", len(files))
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
