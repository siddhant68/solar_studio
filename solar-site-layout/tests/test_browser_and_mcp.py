"""S02 (real MCP client session) and V01-V03 (real browser) as pytest entries.

Both run real processes: the MCP SDK client spawns the stdio server; the browser checks
drive Chromium through Playwright against a live local HTTP server. Evidence files are
written to $SOLAR_EVIDENCE_DIR when set (used by scripts/run_acceptance.py).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from conftest import FIXTURES
from helpers_proc import ROOT


def evidence_dir(tmp_path: Path, name: str) -> Path:
    base = os.environ.get("SOLAR_EVIDENCE_DIR")
    d = Path(base) / name if base else tmp_path / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def test_s02_real_mcp_client_session(tmp_path):
    out = evidence_dir(tmp_path, "mcp")
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "mcp_session.py"), str(out), str(tmp_path / "mcp-data")], capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    assert p.returncode == 0, p.stdout + p.stderr
    steps = json.loads((out / "mcp-session-steps.json").read_text())["steps"]
    assert len(steps) >= 17 and all(s["ok"] for s in steps)
    wire = [json.loads(line) for line in (out / "mcp-wire-transcript.jsonl").read_text().splitlines()]
    assert wire[0]["message"]["method"] == "initialize"
    assert any(m["message"].get("method") == "tools/list" for m in wire)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


BROWSER_DIR = ROOT / "tests" / "browser"
PINNED_PLAYWRIGHT = json.loads((BROWSER_DIR / "package.json").read_text())["dependencies"]["playwright"]


def _browser_tooling_problem() -> str | None:
    """None when node resolves the pinned Playwright from tests/browser (its own
    node_modules from scripts/bootstrap_browser.sh, or an identical preinstalled copy)."""
    if not shutil.which("node"):
        return "node is not installed"
    p = subprocess.run(["node", "-p", "require('playwright/package.json').version"], capture_output=True, text=True, cwd=str(BROWSER_DIR))
    if p.returncode != 0:
        return "playwright is not resolvable from tests/browser; run scripts/bootstrap_browser.sh"
    if p.stdout.strip() != PINNED_PLAYWRIGHT:
        return f"playwright {p.stdout.strip()} found, {PINNED_PLAYWRIGHT} pinned; run scripts/bootstrap_browser.sh"
    return None


def test_v01_v02_v03_real_browser(tmp_path):
    problem = _browser_tooling_problem()
    if problem:
        # Acceptance runs and CI set SOLAR_REQUIRE_BROWSER=1 so missing tooling fails
        # loudly instead of skipping unnoticed.
        if os.environ.get("SOLAR_REQUIRE_BROWSER") == "1":
            pytest.fail(f"real-browser checks required but cannot run: {problem}")
        pytest.skip(problem)
    out = evidence_dir(tmp_path, "browser")
    port = _free_port()
    data = tmp_path / "ui-data"
    server = subprocess.Popen(
        [sys.executable, "-m", "solar_layout.cli", "--data-dir", str(data), "serve", "--port", str(port)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        p = subprocess.run(
            ["node", str(BROWSER_DIR / "ui_checks.cjs"), f"http://127.0.0.1:{port}", str(out), str(FIXTURES)],
            capture_output=True,
            text=True,
            timeout=900,
            cwd=str(BROWSER_DIR),
        )
    finally:
        server.terminate()
        server.wait(timeout=20)
    report = json.loads((out / "ui-checks.json").read_text())
    assert p.returncode == 0 and report["passed"], p.stdout + p.stderr
    names = {r["name"] for r in report["results"]}
    assert any(n.startswith("V01") for n in names) and any(n.startswith("V02") for n in names) and any(n.startswith("V03") for n in names)
    # the review regressions (F1 create/update delay, F2 stale SVG, switch/import while pending)
    for needle in ("F1 create", "F1 update", "F2 stale SVG", "project switch", "import while"):
        assert any(needle in n for n in names), needle


@pytest.mark.parametrize("required", [True, False])
def test_missing_browser_tooling_fails_when_required_and_skips_otherwise(tmp_path, required):
    """The tooling check above was dead code in d935ff2 (the browser test ran unconditionally
    and crashed with FileNotFoundError when node was absent). Run the browser test in a child
    pytest whose PATH has no node: with SOLAR_REQUIRE_BROWSER=1 it must FAIL with the reason;
    without it, it must SKIP with the reason."""
    bin_dir = tmp_path / "bin-without-node"
    bin_dir.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("SOLAR_REQUIRE_BROWSER", "SOLAR_EVIDENCE_DIR", "NODE_PATH")}
    env["PATH"] = str(bin_dir)
    if required:
        env["SOLAR_REQUIRE_BROWSER"] = "1"
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfEs", "tests/test_browser_and_mcp.py::test_v01_v02_v03_real_browser"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=300,
    )
    out = p.stdout + p.stderr
    if required:
        assert p.returncode != 0 and "FAILED tests/test_browser_and_mcp.py::test_v01_v02_v03_real_browser" in out, out[-2000:]
        assert "required but cannot run: node is not installed" in out, out[-2000:]
    else:
        assert p.returncode == 0 and "SKIPPED [1]" in out and "node is not installed" in out, out[-2000:]
