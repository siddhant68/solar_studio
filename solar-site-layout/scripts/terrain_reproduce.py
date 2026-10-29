"""TD03: reproduce Module 02 T1 from a fresh clone of the pushed branch.

    python scripts/terrain_reproduce.py OUT_DIR [--ref BRANCH] [--remote URL]

Clones the branch from GitHub into an empty temporary directory, installs strictly from
uv.lock with an empty uv cache, bootstraps the pinned browser tooling, runs the analytic
terrain CLI workflow (T01 planar, T03 interior hill, T04 void) and checks the expected
numbers, then runs the full test suite with the real browser required. Writes
OUT_DIR/reproduction.json and OUT_DIR/reproduction-log.txt. The clone's git tree IDs of
the source, tests, scripts and contract package are recorded so the evidence stays bound
to the code it reproduced.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REMOTE = "https://github.com/siddhant68/solar_studio"
TREES = ("solar-site-layout/src", "solar-site-layout/tests", "solar-site-layout/scripts", "handoffs/module-02-terrain/contracts", "handoffs/module-02-terrain/fixtures", ".github")


def run(cmd, cwd=None, env=None, timeout=3600):
    return subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def main() -> int:
    out = Path(sys.argv[1]).resolve()
    ref = sys.argv[sys.argv.index("--ref") + 1] if "--ref" in sys.argv else "feat/module-02-terrain-t1"
    remote = sys.argv[sys.argv.index("--remote") + 1] if "--remote" in sys.argv else REMOTE
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="terrain-repro-"))
    log: list[str] = []
    steps: dict[str, dict] = {}
    env = dict(os.environ)
    env["UV_CACHE_DIR"] = str(tmp / "uv-cache")
    env.pop("VIRTUAL_ENV", None)
    for k in ("SOLAR_EVIDENCE_DIR", "SOLAR_DATA_DIR", "SOLAR_FAULT_POINT"):
        env.pop(k, None)

    def step(name, cmd, cwd, extra_env=None, timeout=3600):
        e = dict(env)
        if extra_env:
            e.update(extra_env)
        t0 = time.time()
        p = run(cmd, cwd=cwd, env=e, timeout=timeout)
        dt = time.time() - t0
        shown = " ".join(str(c).replace(str(tmp), "<tmp>") for c in cmd)
        log.append(f"$ {shown}\n# exit {p.returncode} in {dt:.1f}s\n{p.stdout[-4000:]}\n{p.stderr[-2000:]}\n")
        steps[name] = {"exit": p.returncode, "seconds": round(dt, 1)}
        return p

    try:
        clone = tmp / "solar_studio"
        step("git clone", ["git", "clone", "-q", "--branch", ref, remote, clone], None)
        head = run(["git", "-C", clone, "rev-parse", "HEAD"]).stdout.strip()
        trees = {t: run(["git", "-C", clone, "rev-parse", f"HEAD:{t}"]).stdout.strip() for t in TREES}
        app = clone / "solar-site-layout"
        step("uv sync --frozen", ["uv", "sync", "--frozen", "--python", "3.12"], app)
        boot = step("bootstrap browser", ["bash", "scripts/bootstrap_browser.sh"], app)
        cli = [app / ".venv/bin/solar-layout", "--data-dir", tmp / "data"]
        fx = clone / "handoffs/module-02-terrain/fixtures"
        checks: dict[str, bool] = {}
        for cid in ("T01", "T03", "T04"):
            case = json.loads((fx / "cases" / f"{cid}.json").read_text())
            req = tmp / f"{cid}.request.json"
            req.write_text(json.dumps(case["placement_request"]))
            p1 = step(f"{cid} generate", [*cli, "generate", (fx / case["layout"]["request"]).resolve()], app)
            p2 = step(f"{cid} terrain import", [*cli, "terrain", "import", (fx / "cases" / case["surface"]).resolve()], app)
            p3 = step(f"{cid} terrain place", [*cli, "terrain", "place", req], app)
            ok = p1.returncode == p2.returncode == p3.returncode == 0
            if not ok:
                checks[cid] = False
                continue
            pid = json.loads(p3.stdout)["result"]["placement_id"]
            items = json.loads(step(f"{cid} terrain items", [*cli, "terrain", "items", pid, "--kind", "tables", "--limit", "500"], app).stdout)["result"]["items"]
            for fmt in ("json", "csv", "supports_csv"):
                ok &= step(f"{cid} terrain export {fmt}", [*cli, "terrain", "export", pid, "--format", fmt], app).returncode == 0
            ok &= json.loads(step(f"{cid} terrain verify", [*cli, "terrain", "verify", pid], app).stdout)["result"]["ok"] is True
            for e, g in zip(case["expected"]["tables"], items):
                ok &= g["status"] == e["status"]
                for k in ("lower_edge_z_m", "min_clearance_m", "covered_area_m2", "uncovered_area_m2"):
                    if k in e:
                        ok &= abs(g[k] - e[k]) <= 1e-9
            checks[cid] = bool(ok and len(items) == len(case["expected"]["tables"]))
        browser_ok = boot.returncode == 0
        test_env = {"SOLAR_REQUIRE_BROWSER": "1"} if browser_ok else {}
        pt = step("pytest (full suite)", [app / ".venv/bin/python", "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=", "-q", "-rfEs"], app, test_env)
        tail = (pt.stdout.strip().splitlines() or [""])[-1]
        steps["pytest (full suite)"]["tail"] = tail
        steps["pytest (full suite)"]["browser_required"] = browser_ok
        rep = {
            "gate": "TD03",
            "passed": all(v["exit"] == 0 for v in steps.values()) and all(checks.values()) and browser_ok and " passed" in tail and "failed" not in tail and "skipped" not in tail,
            "source": f"git clone --branch {ref} {remote} into an empty temporary directory",
            "head": head,
            "trees": trees,
            "uv": run(["uv", "--version"]).stdout.strip(),
            "uv_cache": "empty temporary UV_CACHE_DIR (every package fetched per uv.lock)",
            "analytic_cli_checks": checks,
            "steps": steps,
            "commands": [
                f"git clone --branch {ref} {remote} solar_studio && cd solar_studio/solar-site-layout",
                "UV_CACHE_DIR=$(mktemp -d) uv sync --frozen --python 3.12",
                "scripts/bootstrap_browser.sh",
                ".venv/bin/solar-layout --data-dir DATA generate <case layout request>",
                ".venv/bin/solar-layout --data-dir DATA terrain import <case surface>",
                ".venv/bin/solar-layout --data-dir DATA terrain place <case placement request>",
                ".venv/bin/solar-layout --data-dir DATA terrain items|export|verify <placement_id>",
                "SOLAR_REQUIRE_BROWSER=1 .venv/bin/python -m pytest -p no:cacheprovider",
            ],
            "private_paths_or_accounts_needed": "none",
        }
        (out / "reproduction.json").write_text(json.dumps(rep, indent=1) + "\n")
        (out / "reproduction-log.txt").write_text("\n".join(log))
        print(json.dumps({"passed": rep["passed"], "head": head, "checks": checks, "pytest": tail}, indent=1))
        return 0 if rep["passed"] else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
