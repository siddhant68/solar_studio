"""Provenance shared by terrain imports and placements: versions, source commit, dependencies."""

from __future__ import annotations

import os
import platform
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def dependency_versions() -> dict[str, str]:
    import numpy
    import shapely

    out = {"python": platform.python_version(), "numpy": numpy.__version__, "shapely": shapely.__version__, "geos": shapely.geos_version_string}
    for pkg in ("jsonschema", "starlette", "uvicorn", "mcp"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "not installed"
    return out


def source_commit() -> tuple[str | None, bool | None]:
    env = os.environ.get("SOLAR_SOURCE_COMMIT")
    if env:
        return env, None
    try:
        head = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        if head.returncode != 0:
            return None, None
        dirty = subprocess.run(["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--", "solar-site-layout/src"], capture_output=True, text=True, timeout=5)
        return head.stdout.strip(), bool(dirty.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None, None


def platform_text() -> str:
    return f"{platform.system()} {platform.machine()}"


def describe(deps: dict[str, Any], commit: tuple[str | None, bool | None]) -> dict[str, Any]:
    return {"source_commit": commit[0], "source_tree_dirty": commit[1], "dependencies": deps, "platform": platform_text()}
