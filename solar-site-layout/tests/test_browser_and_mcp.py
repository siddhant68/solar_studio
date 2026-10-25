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


def _node_playwright() -> bool:
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _node_playwright(), reason="node + playwright not available on this runner")
def test_v01_v02_v03_real_browser(tmp_path):
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
            ["node", str(ROOT / "tests" / "browser" / "ui_checks.cjs"), f"http://127.0.0.1:{port}", str(out), str(FIXTURES)],
            capture_output=True,
            text=True,
            timeout=900,
        )
    finally:
        server.terminate()
        server.wait(timeout=20)
    report = json.loads((out / "ui-checks.json").read_text())
    assert p.returncode == 0 and report["passed"], p.stdout + p.stderr
    names = {r["name"] for r in report["results"]}
    assert any(n.startswith("V01") for n in names) and any(n.startswith("V02") for n in names) and any(n.startswith("V03") for n in names)
