"""Evidence gate for the Module 01 CI job (standard library only).

    python3 .github/scripts/module01_ci.py environment --evidence DIR
    python3 .github/scripts/module01_ci.py check --evidence DIR

`environment` records the tested commit and the tool versions actually used.
`check` fails the job unless the JUnit report shows at least one test and no failures,
errors or skips, and unless the real-browser and real-MCP tests ran and left their
evidence: every browser check passed (V01, V02 including the review regressions, V03)
and every MCP session step succeeded, with a wire transcript that starts with
`initialize`. It does not pin the test count; new tests only need to pass.
Both commands run from `solar-site-layout/` and write JSON next to the evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "solar-site-layout"
REQUIRED_CASES = {
    ("test_browser_and_mcp.py", "test_v01_v02_v03_real_browser"),
    ("test_browser_and_mcp.py", "test_s02_real_mcp_client_session"),
}
REQUIRED_FILES = ("test_review_regressions.py",)
BROWSER_PREFIXES = ("V01", "V02", "V03")
BROWSER_NEEDLES = ("F1 create", "F1 update", "F2 stale SVG", "project switch", "import while")


def run(cmd: list[str], cwd: Path | None = None) -> str | None:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (p.stdout or p.stderr).strip() if p.returncode == 0 else None


def environment(evidence: Path) -> int:
    evidence.mkdir(parents=True, exist_ok=True)
    venv_python = APP / ".venv" / "bin" / "python"
    env = {
        "tested_commit": run(["git", "rev-parse", "HEAD"], APP),
        "github": {k: os.environ.get(k) for k in ("GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_WORKFLOW", "PR_HEAD_SHA", "PR_BASE_SHA")},
        "run_url": f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
        "runner": {"os": os.environ.get("ImageOS") or platform.platform(), "image_version": os.environ.get("ImageVersion"), "arch": platform.machine()},
        "python": run([str(venv_python), "-c", "import sys; print(sys.version.split()[0])"]) if venv_python.exists() else None,
        "uv": run(["uv", "--version"]),
        "node": run(["node", "--version"]),
        "npm": run(["npm", "--version"]),
        "playwright": run(["node", "-p", "require('playwright/package.json').version"], APP / "tests" / "browser"),
        "playwright_pinned": json.loads((APP / "tests" / "browser" / "package.json").read_text())["dependencies"]["playwright"],
    }
    (evidence / "ci-environment.json").write_text(json.dumps(env, indent=1) + "\n")
    print(json.dumps(env, indent=1))
    return 0


def junit_cases(path: Path) -> list[dict]:
    cases = []
    for tc in ET.parse(path).getroot().iter("testcase"):
        outcome = "passed"
        for child in tc:
            if child.tag in ("failure", "error"):
                outcome = child.tag
            elif child.tag == "skipped":
                outcome = "skipped"
        cases.append({"file": tc.get("classname", "").split(".")[-1] + ".py", "name": tc.get("name"), "outcome": outcome})
    return cases


def check(evidence: Path) -> int:
    problems: list[str] = []
    summary: dict = {"evidence_dir": str(evidence)}
    junit = evidence / "pytest-junit.xml"
    cases: list[dict] = []
    if not junit.is_file():
        problems.append("pytest-junit.xml is missing: the test step did not run or did not finish")
    else:
        cases = junit_cases(junit)
        counts: dict[str, int] = {}
        for c in cases:
            counts[c["outcome"]] = counts.get(c["outcome"], 0) + 1
        summary["tests"] = {"total": len(cases), **counts}
        if not cases:
            problems.append("the JUnit report contains no test cases")
        for c in cases:
            if c["outcome"] != "passed":
                problems.append(f"{c['outcome']}: tests/{c['file']}::{c['name']}")
        by_key = {(c["file"], c["name"]): c["outcome"] for c in cases}
        for key in sorted(REQUIRED_CASES):
            if by_key.get(key) != "passed":
                problems.append(f"required test did not pass: tests/{key[0]}::{key[1]} ({by_key.get(key, 'absent')})")
        for f in REQUIRED_FILES:
            sel = [c for c in cases if c["file"] == f]
            if not sel:
                problems.append(f"no test cases from tests/{f}")
    ui_path = evidence / "browser" / "ui-checks.json"
    if not ui_path.is_file():
        problems.append("browser/ui-checks.json is missing: the real-browser checks did not run")
    else:
        ui = json.loads(ui_path.read_text())
        rows = ui.get("results", [])
        failed = [r["name"] for r in rows if not r.get("pass")]
        summary["browser"] = {"checks": len(rows), "failed": failed, "browser": ui.get("browser"), "playwright": ui.get("playwright")}
        if not rows or not ui.get("passed") or failed:
            problems.append(f"browser checks did not all pass: {failed or 'no results'}")
        names = [r["name"] for r in rows]
        for prefix in BROWSER_PREFIXES:
            if not any(n.startswith(prefix) for n in names):
                problems.append(f"no {prefix} browser checks were recorded")
        for needle in BROWSER_NEEDLES:
            if not any(needle in n for n in names):
                problems.append(f"browser regression check '{needle}' was not recorded")
        if not list((evidence / "browser").glob("*.png")):
            problems.append("no browser screenshots were produced")
    steps_path = evidence / "mcp" / "mcp-session-steps.json"
    wire_path = evidence / "mcp" / "mcp-wire-transcript.jsonl"
    if not steps_path.is_file() or not wire_path.is_file():
        problems.append("MCP session evidence (mcp/mcp-session-steps.json, mcp/mcp-wire-transcript.jsonl) is missing")
    else:
        steps = json.loads(steps_path.read_text()).get("steps", [])
        bad = [s.get("name", "?") for s in steps if not s.get("ok")]
        lines = [ln for ln in wire_path.read_text().splitlines() if ln.strip()]
        first = json.loads(lines[0])["message"].get("method") if lines else None
        summary["mcp"] = {"steps": len(steps), "failed": bad, "wire_messages": len(lines), "first_method": first}
        if not steps or bad:
            problems.append(f"MCP session steps did not all succeed: {bad or 'no steps'}")
        if first != "initialize":
            problems.append(f"MCP wire transcript does not start with initialize (got {first!r})")
    summary["passed"] = not problems
    summary["problems"] = problems
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "ci-check.json").write_text(json.dumps(summary, indent=1) + "\n")
    report = ["## Module 01 CI evidence", "", f"**{'PASS' if not problems else 'FAIL'}**", ""]
    if "tests" in summary:
        report.append(f"- Tests: {json.dumps(summary['tests'])}")
    if "browser" in summary:
        b = summary["browser"]
        report.append(f"- Browser checks: {b['checks']} ({len(b['failed'])} failed), browser {json.dumps(b['browser'])}, Playwright {b['playwright']}")
    if "mcp" in summary:
        m = summary["mcp"]
        report.append(f"- MCP session steps: {m['steps']} ({len(m['failed'])} failed), {m['wire_messages']} wire messages")
    report += [f"- Problem: {p}" for p in problems]
    text = "\n".join(report) + "\n"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(text)
    return 0 if not problems else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("environment", "check"))
    ap.add_argument("--evidence", required=True, type=Path)
    args = ap.parse_args()
    return environment(args.evidence) if args.command == "environment" else check(args.evidence)


if __name__ == "__main__":
    sys.exit(main())
