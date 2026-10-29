"""Run the Module 02 T1 acceptance evidence against the current code.

    .venv/bin/python scripts/run_terrain_acceptance.py

Requires a clean working tree for the bound paths. Records their git tree IDs, then runs:
1. the full suite (Module 01 and terrain) with the real browser required, JUnit and
   browser/MCP/terrain-MCP evidence into reports/terrain/acceptance-run/;
2. the CI evidence gate (.github/scripts/module01_ci.py check) on that evidence;
3. the TD02 benchmark into reports/TERRAIN_BENCHMARKS.json.
Then build_terrain_acceptance.py turns the recorded outcomes into TERRAIN_ACCEPTANCE.json.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
RUN = ROOT / "reports" / "terrain" / "acceptance-run"
BOUND = ["solar-site-layout/src", "solar-site-layout/tests", "solar-site-layout/scripts", "solar-site-layout/pyproject.toml", "solar-site-layout/uv.lock", "solar-site-layout/fixtures", "handoffs/module-02-terrain/contracts", "handoffs/module-02-terrain/fixtures", ".github"]


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout.strip()


def trees() -> dict[str, str]:
    return {p: git("rev-parse", f"HEAD:{p}") for p in BOUND}


def main() -> int:
    dirty = git("status", "--porcelain", "--", *BOUND)
    if dirty:
        print("bound paths have uncommitted changes; commit them first:\n" + dirty)
        return 2
    if RUN.exists():
        shutil.rmtree(RUN)
    RUN.mkdir(parents=True)
    manifest = {"head": git("rev-parse", "HEAD"), "trees": trees(), "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    env = {**os.environ, "SOLAR_REQUIRE_BROWSER": "1", "SOLAR_EVIDENCE_DIR": str(RUN)}
    with open(RUN / "pytest-output.txt", "w") as fh:
        p = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=", "-q", "-rfEs", f"--junitxml={RUN / 'pytest-junit.xml'}"], cwd=str(ROOT), env=env, stdout=fh, stderr=subprocess.STDOUT)
    manifest["pytest_exit"] = p.returncode
    g = subprocess.run(["python3", str(REPO / ".github" / "scripts" / "module01_ci.py"), "check", "--evidence", str(RUN)], cwd=str(ROOT), capture_output=True, text=True)
    manifest["ci_gate_exit"] = g.returncode
    b = subprocess.run([sys.executable, str(ROOT / "scripts" / "terrain_benchmark.py"), str(ROOT / "reports" / "TERRAIN_BENCHMARKS.json")], cwd=str(ROOT), capture_output=True, text=True)
    manifest["benchmark_exit"] = b.returncode
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if git("rev-parse", "HEAD") != manifest["head"] or trees() != manifest["trees"]:
        manifest["error"] = "the bound code changed while the evidence was being produced"
    (RUN / "run-manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    # pytest's tmp data directories are not evidence
    for d in RUN.glob("**/data"):
        shutil.rmtree(d, ignore_errors=True)
    print(json.dumps(manifest, indent=1))
    return 0 if p.returncode == g.returncode == b.returncode == 0 and "error" not in manifest else 1


if __name__ == "__main__":
    sys.exit(main())
