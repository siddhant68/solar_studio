"""Build reports/ACCEPTANCE.json: all 36 gates with pass/fail/blocked/unexecuted.

    .venv/bin/python scripts/build_acceptance_report.py

Statuses come from recorded outcomes only: JUnit test cases from scripts/run_acceptance.py,
browser/MCP step files, benchmark gates, reference evidence files and the packaging /
fresh-checkout logs. Missing evidence makes a gate "unexecuted", never "pass".
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
ACC = ROOT / "evidence" / "acceptance"
DELIV = ROOT / "evidence" / "delivery"
SOURCE_PATHS = ["solar-site-layout/src", "solar-site-layout/tests", "solar-site-layout/scripts", "solar-site-layout/pyproject.toml", "solar-site-layout/uv.lock", "solar-site-layout/fixtures", "solar-site-layout/references/probes"]

TITLES = {
    "R01": "Reference commit/build, file hashes, runtime and licence findings recorded",
    "R02": "Real REA JavaScript analysis of the selected built reference artifact retained and parseable",
    "R03": "Three repeatable local reference scenarios with honest REA-versus-Playwright attribution",
    "R04": "Reference findings affect implementation decisions; JS/WASM coverage limits explicit",
    "C01": "Versioned schemas reject bad units/frames, NaN/Inf, bad rings/holes, degree/Z inputs with typed field errors",
    "C02": "Rectangle fixture: 6 tables, 24 modules, 13.2 kWp, 168/120/48 m2, all origins",
    "C03": "Obstacle fixture: 5 tables, 20 modules, 11 kWp, table (4,1) rejected, 112 m2",
    "C04": "Portrait/landscape, gaps and tilt dimensions; module vs envelope area",
    "C05": "3-4-5 pitch fixture and flat / clearance / invalid / near-horizon cases",
    "C06": "Azimuth axes, corners and relative heights (0/90/180/270, 17/37/73)",
    "C07": "Concave notch and hole: full footprint validity, not sampled points",
    "C08": "MultiPolygon components; complete exclusion gives an empty layout with null ratios",
    "C09": "Setback/keepout against original geometry; arcs and tangency safe",
    "C10": "No overlap, exact membership, totals agree; verifier detects corruption",
    "C11": "21 translated/azimuth pairs: same membership, corners within 1e-6 m",
    "C12": "Envelope, extent, dimension and candidate/output limits enforced before unbounded work",
    "C13": "Nine phase candidates, selected >= phase zero, tie-break, scores, bounded-optimality label",
    "C14": "Normalization and repeat runs give identical payload digests; geometry change changes identity",
    "S01": "CLI and HTTP: same summary/result identity and same domain errors",
    "S02": "Real MCP client session: initialize, list, project, pitch, generate, page, export; transcript retained",
    "S03": "Same service and store across MCP/HTTP/CLI; transport schemas documented",
    "S04": "Two processes, one expected revision: exactly one succeeds",
    "S05": "Restart reads everything; interrupted generation/export leaves no partial success",
    "S06": "Bounded stable paging; typed invalid cursor/range; summary/page reads do not load coordinates",
    "S07": "Export paths stay inside the managed root; no shell interpolation",
    "V01": "Real browser: import, edit, generate, totals, save/reload, download, screenshot",
    "V02": "Delayed generation: old result historical, edits dirty, no overwrite of newer selection",
    "V03": "Plan renders at overview and close-up for analytic, concave/hole and projected fixtures",
    "V04": "SVG/DXF/CSV/JSON match the immutable result",
    "V05": "Calculation report arithmetic, denominators and stated assumptions",
    "D01": "Fresh checkout installs from locks and reproduces the CLI workflow and tests",
    "D02": ">= 10,000 modules generate+verify <= 20 s and <= 512 MiB peak process-tree memory",
    "D03": "25,000-module stress completes or is rejected by a declared limit; bounds and timeout demonstrated",
    "D04": "Tests, browser checks, MCP smoke and benchmark run against the final code; evidence bound to commit",
    "D05": "Source archive and Git bundle with SHA-256; integrity checked; no caches/credentials/giant checkouts",
    "D06": "Delivery report separates verified behaviour, observations, assumptions, untested platforms, failures; licences",
}

TEST_MAP = {
    "C01": [("test_validation.py", "test_")],
    "C02": [("test_fixtures_analytic.py", "test_c02_")],
    "C03": [("test_fixtures_analytic.py", "test_c03_"), ("test_fixtures_analytic.py", "test_obstacle_exact_tangency")],
    "C04": [("test_geometry_conventions.py", "test_c04_")],
    "C05": [("test_pitch.py", "test_")],
    "C06": [("test_geometry_conventions.py", "test_c06_"), ("test_geometry_conventions.py", "test_azimuth_normalization")],
    "C07": [("test_fixtures_analytic.py", "test_c07_"), ("test_fixtures_analytic.py", "test_corner_only")],
    "C08": [("test_fixtures_analytic.py", "test_c08_"), ("test_fixtures_analytic.py", "test_multipolygon_")],
    "C09": [("test_tolerance_and_arcs.py", "test_")],
    "C10": [("test_verifier_translation_phase_identity.py", "test_c10_"), ("test_review_regressions.py", "test_f5_")],
    "C11": [("test_verifier_translation_phase_identity.py", "test_c11_")],
    "C12": [("test_validation.py", n) for n in ("test_coordinate_magnitude_limit", "test_site_diagonal_limit", "test_module_dimension_envelope", "test_anchor_must_be_near_site", "test_candidate_limit", "test_module_output_limit", "test_timeout_policy", "test_timeout_covers")],
    "C13": [("test_verifier_translation_phase_identity.py", "test_c13_")],
    "C14": [("test_verifier_translation_phase_identity.py", "test_c14_")],
    "S01": [("test_service_interfaces.py", "test_s01_")],
    "S02": [("test_browser_and_mcp.py", "test_s02_")],
    "S03": [("test_service_interfaces.py", "test_s03_"), ("test_service_interfaces.py", "test_selection_bound")],
    "S04": [("test_service_interfaces.py", "test_s04_")],
    "S05": [("test_service_interfaces.py", "test_s05_"), ("test_review_regressions.py", "test_f3_")],
    "S06": [("test_service_interfaces.py", "test_s06_")],
    "S07": [("test_service_interfaces.py", "test_s07_")],
    "V01": [("test_browser_and_mcp.py", "test_v01_")],
    "V02": [("test_browser_and_mcp.py", "test_v01_")],
    "V03": [("test_browser_and_mcp.py", "test_v01_")],
    "V04": [("test_exports.py", "test_v04_"), ("test_review_regressions.py", "test_f3_"), ("test_review_regressions.py", "test_f4_"), ("test_review_regressions.py", "test_exports_identical_across")],
    "V05": [("test_exports.py", "test_v05_")],
}

EVIDENCE = {
    "C02": ["evidence/examples/rectangle/"],
    "C03": ["evidence/examples/obstacle/"],
    "C05": ["evidence/examples/pitch-3-4-5.result.json"],
    "C07": ["evidence/examples/concave-notch/", "evidence/examples/hole/"],
    "C08": ["evidence/examples/multipolygon/"],
    "S02": ["evidence/acceptance/mcp/mcp-wire-transcript.jsonl", "evidence/acceptance/mcp/mcp-session-steps.json", "evidence/acceptance/mcp-inspector/"],
    "S06": ["evidence/acceptance/S06-memory.json"],
    "V01": ["evidence/acceptance/browser/ui-checks.json", "evidence/acceptance/browser/V01-app-after-generate.png", "evidence/acceptance/browser/V01-app-after-reload.png"],
    "V02": ["evidence/acceptance/browser/V02-late-result-outdated.png", "evidence/acceptance/browser/V02-late-response-not-overwriting.png", "evidence/acceptance/browser/V02-F1-create-delay.png", "evidence/acceptance/browser/V02-F1-update-delay.png", "evidence/acceptance/browser/V02-F2-stale-svg-released.png", "evidence/acceptance/browser/V02-project-switch-while-pending.png", "evidence/acceptance/browser/V02-import-while-pending.png", "evidence/repair/"],
    "V04": ["evidence/examples/*/plan.svg|plan.dxf|modules.csv|layout.json", "evidence/repair/"],
    "C10": ["evidence/repair/"],
    "S05": ["evidence/repair/"],
    "V03": ["evidence/acceptance/browser/V03-*-overview.png", "evidence/acceptance/browser/V03-*-closeup.png"],
    "V05": ["evidence/examples/*/report.md"],
}


# Regressions for the independent review of 2026-10-26 (reviews/module-01/2026-10-26/),
# associated with the original gates they belong to.
REVIEW_NOTES = {
    "V01": "Review 2026-10-26: the resource 404 (/favicon.ico) is fixed; the 'no browser errors' checks run full Chromium and fail on any console error, failed request or HTTP status >= 400, logged with its URL.",
    "V02": "Review 2026-10-26 regressions F1 (create- and update-delay edits) and F2 (stale SVG; project switch and import while pending) are the V02 rows of ui-checks.json.",
    "V04": "Review 2026-10-26 regressions F3 (concurrent exports) and F4 (result-only, write-once exports; separate context export), plus the PYTHONHASHSEED-dependent DXF bytes found during the repair, are in tests/test_review_regressions.py.",
    "S05": "Review 2026-10-26 regression F3: parallel and overlapping exports leave no failed call and no stray .partial files (tests/test_review_regressions.py::test_f3_*).",
    "C12": "Re-running D03 after the review repair showed the generation time limit was checked only inside the layout engine; it now also covers record construction and verification before anything is persisted (tests/test_validation.py::test_timeout_covers_records_and_verification_not_only_compute).",
    "C10": "Review 2026-10-26 regression F5: per-record fields, record totals, independently computed areas and payload integrity (tests/test_review_regressions.py::test_f5_*).",
}
SUPERSEDES = {
    "previous_acceptance_source_commit": "f16944e8e9050aaf1078a3a07fcf2115805bc4e4",
    "previous_result": "36/36 pass, recorded in delivery commit f55f4be",
    "why_superseded": "The independent review of 2026-10-26 (reviews/module-01/2026-10-26/) reproduced five defects at f55f4be (F1 input snapshot across autosave, F2 stale SVG render, F3 concurrent export collisions, F4 mutable export context, F5 verifier gaps) and a browser resource 404. The earlier passes for V01, V02, V04, S05 and C10 rested on evidence that did not exercise those cases. This table is rebuilt from a new run on the repaired source.",
}


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True).stdout.strip()


def load(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def gate_from_tests(gate: str, cases: list[dict]):
    sel = []
    for f, prefix in TEST_MAP[gate]:
        sel += [c for c in cases if c["file"] == f and c["name"].startswith(prefix)]
    if not sel:
        return "unexecuted", []
    names = [f"tests/{c['file']}::{c['name']}" for c in sel]
    if any(c["outcome"] == "failed" for c in sel):
        return "fail", names
    if all(c["outcome"] == "skipped" for c in sel):
        return "unexecuted", names
    return "pass", names


def browser_checks(prefix: str) -> tuple[bool | None, list[str]]:
    ui = load(ACC / "browser" / "ui-checks.json")
    if not ui:
        return None, []
    rows = [r for r in ui["results"] if r["name"].startswith(prefix)]
    return (bool(rows) and all(r["pass"] for r in rows)), [r["name"] + (" PASS" if r["pass"] else " FAIL") for r in rows]


def main() -> int:
    meta = load(ACC / "run-meta.json")
    cases = load(ACC / "pytest-cases.json") or []
    if not meta:
        print("run scripts/run_acceptance.py first")
        return 2
    commit = meta["source_commit"]
    head = git("rev-parse", "HEAD")
    head_tree = {p: git("rev-parse", f"HEAD:{p}") for p in SOURCE_PATHS}
    bound = head_tree == meta["source_tree_ids"]
    gates = []

    def add(gid, status, commands, evidence, tests=None, notes=""):
        gates.append({"gate": gid, "title": TITLES[gid], "status": status, "source_commit": commit, "commands": commands, "evidence": evidence, "tests": tests or [], "notes": notes})

    test_cmd = [meta["pytest"]["command"], ".venv/bin/python scripts/run_acceptance.py --inspector-dir <npm install of @modelcontextprotocol/inspector@2.12.0>"]

    # ---- reference gates ----------------------------------------------------------------
    man = load(ROOT / "references" / "manifest.json")
    ok = bool(man and man["references"][0]["built_artifact"]["files"] and man["references"][0]["licences"] and man["references"][1]["licence_observation"])
    add("R01", "pass" if ok else "unexecuted", ["python -I references/probes/build_manifest.py DIST AGV PVPLANT REA_DIR BUILD_LOG references/manifest.json"], ["references/manifest.json", "reports/REFERENCE_FINDINGS.md"],
        notes="Pinned commit used (no substitution); 35 built files hashed; Apache-2.0 / CC BY 4.0 / NOTICE recorded; PVPlant LGPL-2-or-later headers with no licence file at the pin.")
    st = ROOT / "evidence" / "rea" / "static"
    summ = load(st / "attempt4-html-worker-chunks.summary.json")
    exit4 = (st / "attempt4-html-worker-chunks.exit").read_text().strip() if (st / "attempt4-html-worker-chunks.exit").exists() else ""
    try:
        bundle = json.loads(gzip.open(st / "attempt4-html-worker-chunks.evidence-bundle.json.gz").read())
        parse_ok = bundle["records"][0]["operation"] == "analyze_javascript_application"
        ev_id = bundle["records"][0]["evidence_id"]
    except (OSError, ValueError, KeyError):
        parse_ok, ev_id = False, None
    cov = load(ROOT / "evidence" / "rea" / "execution" / "coverage-matches.json")
    a3 = load(st / "attempt3-index-reduced-limits.summary.json") or load(st / "attempt3-index-reduced-limits.error.json")
    a3_status = "completed" if (st / "attempt3-index-reduced-limits.summary.json").exists() else ("timed out" if a3 else "not recorded")
    r02 = summ is not None and exit4.startswith("exit=0") and parse_ok
    add("R02", "pass" if r02 else "fail", ["npx --no-install rea analyze-javascript-application <dist> --detail summary --evidence_output <bundle> --source-path index.html --source-path assets/entry.worker-BWZeDHYo.js --source-path assets/rows-06xZe35N.js --source-path assets/recommend-CNrji3tC.js --format json",
        "node references/probes/agv_rea_execution_probe.cjs http://127.0.0.1:4173/ <out> <rea dir> <node24 bin>"],
        ["evidence/rea/static/", "evidence/rea/execution/"],
        notes=f"Static REA analysis completed (exit 0, evidence {ev_id}) for index.html + worker + rows + recommend chunks. The main 917 kB chunk (index-8KvU91kB.js) did not finish REA static analysis: 300 s and 1,500 s timeouts, then reduced-limit attempt 3 {a3_status}. "
              "The row-pitch UI/state path in that chunk was located with REA observe_web_execution (CDP precise coverage) instead: "
              + ("; ".join(f"{m['name'] or 'anon'}@{m['start']}-{m['end']}" for m in (cov or {"scripts": [{"matches": []}]})["scripts"][0]["matches"][:6]) if cov else "coverage evidence missing"))
    scen = ROOT / "evidence" / "rea" / "runtime-scenarios"
    s_ok = []
    for s in ("R03-S1-small-array", "R03-S2-change-pitch-tilt", "R03-S3-save-reload"):
        d = load(scen / s / "summary.json")
        s_ok.append(bool(d) and d["completeness"]["status"] == "complete" and all(x["status"] == "completed" for x in d["steps"]))
    pw = load(ROOT / "evidence" / "runtime" / "agv" / "playwright-scenarios.json")
    add("R03", "pass" if all(s_ok) and pw else "fail", ["npx --no-install rea capture-browser-scenario references/scenarios/<scenario>.rea-scenario.json --format json", "node references/probes/agv_playwright_scenarios.cjs http://127.0.0.1:4173/ <out>"],
        ["evidence/rea/runtime-scenarios/", "evidence/runtime/agv/"], notes="REA capture_browser_scenario (REA Evidence: steps, screenshots, DOM, hashed storage) plus a separately labelled Playwright companion that reads stored design JSON and live input values.")
    findings = (ROOT / "reports" / "REFERENCE_FINDINGS.md").read_text() if (ROOT / "reports" / "REFERENCE_FINDINGS.md").exists() else ""
    r04 = findings.count("| D") >= 2 and "WASM" in findings and "unknown" in findings.lower()
    add("R04", "pass" if r04 else "unexecuted", ["(review) reports/REFERENCE_FINDINGS.md"], ["reports/REFERENCE_FINDINGS.md"], notes="Decision table rows D1..Dn cite the evidence that changed or confirmed an implementation decision; WASM internals are marked unknown.")

    # ---- test-mapped gates --------------------------------------------------------------------
    for gid in ("C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11", "C12", "C13", "C14", "S01", "S02", "S03", "S04", "S05", "S06", "S07", "V04", "V05"):
        status, names = gate_from_tests(gid, cases)
        notes = ""
        if gid == "S02" and meta.get("inspector"):
            notes = f"Also cross-checked with a second client implementation (MCP Inspector CLI 2.12.0, TypeScript SDK): {json.dumps(meta['inspector'])}"
        if gid == "S03":
            notes = "Transport schemas documented in docs/CONTRACTS.md section 7; MCP tool input schemas embed the JSON Schemas."
        if gid in REVIEW_NOTES:
            notes = (notes + " " if notes else "") + REVIEW_NOTES[gid]
        add(gid, status, test_cmd, EVIDENCE.get(gid, []), names, notes)
    for gid, prefix in (("V01", "V01"), ("V02", "V02"), ("V03", "V03")):
        status, names = gate_from_tests(gid, cases)
        bok, rows = browser_checks(prefix)
        if status == "pass" and bok is False:
            status = "fail"
        if bok is None:
            status = "unexecuted"
        notes = "; ".join(rows)
        if gid == "V03":
            notes += ". Overview and close-up PNGs were also inspected visually in the build session (north arrow, scale, legend, boundaries, keepout arcs, 0.02 m module gaps, side-panel text clear of the plan)."
        if gid in REVIEW_NOTES:
            notes += ". " + REVIEW_NOTES[gid]
        add(gid, status, test_cmd, EVIDENCE.get(gid, []), names, notes)

    # ---- delivery gates ---------------------------------------------------------------------
    repro = load(DELIV / "reproduction.json")
    add("D01", "pass" if repro and repro.get("passed") else ("fail" if repro else "unexecuted"), (repro or {}).get("commands", ["scripts/package_delivery.py"]), ["evidence/delivery/reproduction.json", "evidence/delivery/reproduction-log.txt"],
        notes=(repro or {}).get("summary", "fresh clone from the Git bundle, uv sync --frozen, CLI analytic workflow, full pytest"))
    bench = load(ROOT / "reports" / "BENCHMARKS.json")
    if bench:
        d02 = next(c for c in bench["cases"] if c["case"] == "D02-10k")
        add("D02", "pass" if d02["gate"]["pass"] else "fail", [".venv/bin/python scripts/benchmark.py reports/BENCHMARKS.json"], ["reports/BENCHMARKS.json"], notes=json.dumps(d02["gate"]))
        d03 = [c for c in bench["cases"] if c["case"].startswith("D03")]
        ok3 = all(c["gate"].get("pass", c["gate"].get("completed")) for c in d03)
        add("D03", "pass" if ok3 else "fail", [".venv/bin/python scripts/benchmark.py reports/BENCHMARKS.json"], ["reports/BENCHMARKS.json"], notes="; ".join(f"{c['case']}: {json.dumps(c['gate'])}" for c in d03))
    else:
        add("D02", "unexecuted", [], [])
        add("D03", "unexecuted", [], [])
    all_ran = meta["pytest"]["exit"] == 0 and bench is not None and (ACC / "browser" / "ui-checks.json").exists() and (ACC / "mcp" / "mcp-session-steps.json").exists()
    add("D04", "pass" if (all_ran and bound) else "fail", test_cmd + [".venv/bin/python scripts/build_acceptance_report.py"], ["evidence/acceptance/run-meta.json", "evidence/acceptance/pytest-junit.xml"],
        notes=f"pytest exit {meta['pytest']['exit']} over {meta['test_count']} cases on source commit {commit}; source tree of HEAD {head} {'matches' if bound else 'DOES NOT match'} the tested tree ids (src, tests, scripts, locks, fixtures, probes).")
    pkg = load(DELIV / "package-verification.json")
    add("D05", "pass" if pkg and pkg.get("passed") else ("fail" if pkg else "unexecuted"), (pkg or {}).get("commands", ["scripts/package_delivery.py"]), ["evidence/delivery/package-verification.json"], notes=(pkg or {}).get("summary", ""))
    rep = (ROOT / "DELIVERY_REPORT.md").read_text() if (ROOT / "DELIVERY_REPORT.md").exists() else ""
    needed = ["Verified behaviour", "Reference-derived observations", "Modelling assumptions", "Untested platforms", "Remaining failures", "Licences"]
    add("D06", "pass" if all(n in rep for n in needed) else "unexecuted", ["(review) DELIVERY_REPORT.md"], ["DELIVERY_REPORT.md"], notes="Sections present: " + ", ".join(n for n in needed if n in rep))

    order = list(TITLES)
    gates.sort(key=lambda g: order.index(g["gate"]))
    counts: dict[str, int] = {}
    for g in gates:
        counts[g["status"]] = counts.get(g["status"], 0) + 1
    out = {
        "schema": "solar.acceptance/1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": commit,
        "source_tree_ids": meta["source_tree_ids"],
        "head_at_generation": head,
        "head_source_tree_matches_tested": bound,
        "test_cases": len(cases),
        "test_cases_failed": sum(1 for c in cases if c["outcome"] == "failed"),
        "test_cases_skipped": sum(1 for c in cases if c["outcome"] == "skipped"),
        "gate_counts": counts,
        "complete": counts.get("pass", 0) == 36,
        "supersedes": SUPERSEDES,
        "review_regressions": {g: n for g, n in REVIEW_NOTES.items()},
        "tooling": meta.get("tooling"),
        "gates": gates,
    }
    (ROOT / "reports" / "ACCEPTANCE.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(counts), "bound" if bound else "NOT BOUND")
    for g in gates:
        print(g["gate"], g["status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
