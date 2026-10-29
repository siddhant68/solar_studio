"""Build reports/TERRAIN_ACCEPTANCE.json: every Module 02 T1 gate as pass, fail, blocked or unexecuted.

    .venv/bin/python scripts/build_terrain_acceptance.py

Statuses come from recorded outcomes only:
* reports/terrain/acceptance-run/ (run_terrain_acceptance.py): JUnit cases, the CI-gate
  check and the terrain MCP session of a full local run with the browser required;
* reports/TERRAIN_BENCHMARKS.json (local) and reports/terrain/ci-run.json with the CI
  benchmark artifact copied to reports/terrain/ci-benchmark/ (GitHub Actions);
* reports/terrain/reproduction/reproduction.json (terrain_reproduce.py, a fresh clone);
* reports/terrain/library-probes-rerun.json and the research and package files.

Each run records the git tree IDs of the bound paths. Evidence whose trees differ from the
current HEAD is stale, and a gate that depends only on stale or missing evidence is
"unexecuted", never "pass". Out-of-scope gates are recorded as unexecuted (out of T1 scope).
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
REPORTS = ROOT / "reports"
TERR = REPORTS / "terrain"
RUN = TERR / "acceptance-run"
PKG = REPO / "handoffs" / "module-02-terrain"
sys.path.insert(0, str(ROOT / "scripts"))
from run_terrain_acceptance import BOUND  # noqa: E402

TITLES = {
    "TR01": "Sources, commits, licences and authorities recorded; observations of other software kept separate",
    "TR02": "Library probes re-run with the recorded versions; behaviours behind the contract decisions unchanged",
    "TR03": "Final schemas valid; fixtures validate; regeneration byte-identical; checker passes; terrain IDs equal the index",
    "TC01": "Invalid surfaces: INVALID_TERRAIN with the field (incl. cracked T-junction) or RESOURCE_LIMIT; nothing stored",
    "TC02": "Typed request errors (frame, datum, expected_vertical, source, result, terrain, unsupported); no transformation",
    "TC03": "T01 planar terrain, six tables: elevations, clearances, supports, slope, 24 modules / 13.2 kWp",
    "TC04": "T02 tilted 3-4-5 table: L = 51.0 m, upper edge 54.0 m, lift +50.2 m, supports 0.75/2.25 m",
    "TC05": "T03 interior hill: L = 11.1 m, minimum clearance 0.5 m at (4, 4), corner value 10.8 m not produced",
    "TC06": "T04 internal void: unknown_ground, 7.0 / 1.0 m2, no elevations, modules or supports",
    "TC07": "T05 survey edge on table edges: covered and placed; tables beyond unknown_ground; 16 modules / 8.8 kWp",
    "TC08": "T06 support-height limit: infeasible, elevations and supports kept, excluded from placed counts",
    "TC09": "T07 slope limit: infeasible (ground_slope_exceeds_limit)",
    "TC10": "T09 rotated 30 deg into EPSG:32633: same IDs and elevations (1e-9 m), plan coordinates within 1e-6 m",
    "TC11": "z_kind terrain_vertical_reference; exact not_computed list; no pile length or embedment field",
    "TC12": "Module 01 result, payload digest and issued exports unchanged (path, bytes, inode)",
    "TC13": "Identities: equivalent inputs give the same IDs (equal to the index); changes change them; repeats reuse",
    "TC14": "Count, envelope and time limits return RESOURCE_LIMIT before unbounded work; nothing stored",
    "TC15": "Generated support rows (T2)",
    "TC16": "DEM import adapter (T3)",
    "TC17": "LandXML import adapter (T3)",
    "TC18": "T11 micro-gap: unknown_ground, uncovered area 2 x (4.000001 - 4) m2 within 1e-12",
    "TC19": "T12 consistent T-junction accepted with the T03 placement; cracked T-junction rejected",
    "TC20": "Status-dependent records validate against the final schema; count relations checked",
    "TC21": "T13 exact support-limit tie: 1.25 m at the limit is placed; a limit 1e-10 m lower is infeasible",
    "TV01": "Verifier passes every fixture; shares no geometry code with the engine; own bounded candidates reported",
    "TV02": "Verifier rejects every T10 corruption naming the failing check",
    "TV03": "Exports round-trip every record; write-once with tamper restore; identical across processes and hash seeds",
    "TV04": "DXF / SVG / report exports (T2)",
    "TS01": "CLI, HTTP and MCP give the same identities and typed errors",
    "TS02": "Bounded stable paging with typed invalid-cursor errors; summary reads load no records",
    "TS03": "Restart reads everything back; a process killed at fault points leaves no rows; the request then succeeds",
    "TS04": "Provenance: algorithm and policy versions, source commit, dependency versions",
    "TS05": "Real MCP client session: import, place, paging, export, typed DATUM_MISMATCH; wire transcript kept",
    "TS06": "Read-only browser view of a placement (T2)",
    "TD01": "GitHub Actions: full suite with browser and MCP required plus terrain, terrain MCP evidence, benchmark job",
    "TD02": "Placement <= 30 s process wall and <= 1 GiB peak process-tree memory (PLAN.md section 11)",
    "TD03": "Fresh clone with a locked install runs the analytic CLI workflow and the full test suite",
    "TD04": "Delivery report separates verified behaviour, implementation claims, research observations and untested behaviour",
}
OUT_OF_SCOPE = {"TC15", "TC16", "TC17", "TV04", "TS06"}

F, E, V, S, C, P = "test_terrain_fixtures.py", "test_terrain_errors.py", "test_terrain_verifier.py", "test_terrain_service.py", "test_terrain_contracts.py", "test_terrain_predicates.py"
TEST_MAP: dict[str, list[tuple[str, str]]] = {
    "TR03": [(C, "test_")],
    "TC01": [(E, "test_tc01_")],
    "TC02": [(E, "test_tc02_"), (E, "test_non_finite_json_text")],
    "TC03": [(F, "test_fixture_case_values[T01]")],
    "TC04": [(F, "test_fixture_case_values[T02]")],
    "TC05": [(F, "test_fixture_case_values[T03]"), (F, "test_tc05_")],
    "TC06": [(F, "test_fixture_case_values[T04]")],
    "TC07": [(F, "test_fixture_case_values[T05]")],
    "TC08": [(F, "test_fixture_case_values[T06]")],
    "TC09": [(F, "test_fixture_case_values[T07]")],
    "TC10": [(F, "test_tc10_")],
    "TC11": [(F, "test_tc20_tc11_")],
    "TC12": [(S, "test_tc12_")],
    "TC13": [(S, "test_tc13_"), (C, "test_terrain_ids_equal_the_fixture_index")],
    "TC14": [(E, "test_tc14_"), (S, "test_http_terrain_body_limit")],
    "TC18": [(F, "test_fixture_case_values[T11]"), (F, "test_tc18_")],
    "TC19": [(F, "test_fixture_case_values[T12]"), (F, "test_tc19_"), (E, "test_tc01_cracked_t_junction")],
    "TC20": [(F, "test_tc20_tc11_"), (F, "test_fixture_case_values[")],
    "TC21": [(F, "test_fixture_case_values[T13]"), (F, "test_tc21_")],
    "TV01": [(F, "test_tv01_"), (V, "test_import_boundary"), (V, "test_verifier_does_not_call_the_engine"), (P, "test_")],
    "TV02": [(V, "test_tv02_"), (V, "test_t10_lists_exactly_these_mutations"), (V, "test_verification_failure_stores_nothing")],
    "TV03": [(S, "test_tv03_")],
    "TS01": [(S, "test_ts01_")],
    "TS02": [(S, "test_ts02_")],
    "TS03": [(S, "test_ts03_")],
    "TS04": [(S, "test_ts04_")],
    "TS05": [(S, "test_ts05_")],
}


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True).stdout.strip()


def current_trees() -> dict[str, str]:
    return {p: git("rev-parse", f"HEAD:{p}") for p in BOUND}


def load(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def junit(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for tc in ET.parse(path).getroot().iter("testcase"):
        outcome = "passed"
        for child in tc:
            if child.tag in ("failure", "error"):
                outcome = "failed"
            elif child.tag == "skipped":
                outcome = "skipped"
        out.append({"file": tc.get("classname", "").split(".")[-1] + ".py", "name": tc.get("name"), "outcome": outcome})
    return out


def main() -> int:
    trees = current_trees()
    head = git("rev-parse", "HEAD")
    manifest = load(RUN / "run-manifest.json") or {}
    run_fresh = manifest.get("trees") == trees and "error" not in manifest
    cases = junit(RUN / "pytest-junit.xml") if run_fresh else []
    gates: dict[str, dict] = {}

    def gate(gid: str, status: str, evidence: list[str], detail: str) -> None:
        gates[gid] = {"title": TITLES[gid], "status": status, "evidence": evidence, "detail": detail}

    for gid, patterns in TEST_MAP.items():
        sel = [c for c in cases if any(c["file"] == f and c["name"].startswith(p) for f, p in patterns)]
        missing = [f"{f}::{p}*" for f, p in patterns if not any(c["file"] == f and c["name"].startswith(p) for c in cases)]
        ev = ["reports/terrain/acceptance-run/pytest-junit.xml"] + [f"tests/{f}::{p}*" for f, p in patterns]
        if not run_fresh:
            gate(gid, "unexecuted", ev, "no local acceptance run bound to the current source trees")
        elif missing:
            gate(gid, "unexecuted", ev, f"no recorded test cases for {missing}")
        elif all(c["outcome"] == "passed" for c in sel):
            gate(gid, "pass", ev, f"{len(sel)} test cases passed")
        else:
            gate(gid, "fail", ev, "failed or skipped: " + ", ".join(f"{c['file']}::{c['name']} ({c['outcome']})" for c in sel if c["outcome"] != "passed"))

    # TS05 also needs the retained session evidence
    steps = load(RUN / "terrain-mcp" / "terrain-mcp-session-steps.json")
    wire = RUN / "terrain-mcp" / "terrain-mcp-wire-transcript.jsonl"
    if gates["TS05"]["status"] == "pass":
        ok = bool(steps) and all(s["ok"] for s in steps["steps"]) and wire.is_file()
        gates["TS05"]["evidence"] += ["reports/terrain/acceptance-run/terrain-mcp/terrain-mcp-session-steps.json", "reports/terrain/acceptance-run/terrain-mcp/terrain-mcp-wire-transcript.jsonl"]
        if not ok:
            gates["TS05"].update(status="fail", detail="the session evidence is missing or has failed steps")
        else:
            gates["TS05"]["detail"] += f"; {len(steps['steps'])} session steps passed, wire transcript retained"

    # TR01: research record
    src = load(PKG / "research" / "SOURCES.json")
    ok = bool(src) and all("authority" in s for s in src["sources"]) and (PKG / "RESEARCH.md").is_file()
    gate("TR01", "pass" if ok else "fail", ["handoffs/module-02-terrain/research/SOURCES.json", "handoffs/module-02-terrain/RESEARCH.md"], f"{len(src['sources']) if src else 0} sources, each with its authority (source-read, runtime-probe, repository-search, not-inspected)")

    # TR02: probe re-run
    new, old = load(TERR / "library-probes-rerun.json"), load(PKG / "research" / "library-probes.json")
    if new is None:
        gate("TR02", "unexecuted", [], "no probe re-run recorded")
    else:
        same = new == old
        vd, tin = new["vertical_datum"], new["tin_across_hole"]
        behaviours = vd["default_result_h_for_input_100m"] == 100.0 and vd["default_accuracy_m"] == -1.0 and tin["value_at_gap_centre_5_5"] is not None
        gate(
            "TR02",
            "pass" if same and behaviours else "fail",
            ["reports/terrain/library-probes-rerun.json", "handoffs/module-02-terrain/research/library-probes.json", "tests/test_terrain_errors.py::test_tc02_no_transformation_library_is_used"],
            f"re-run with {new['versions']} is {'identical to' if same else 'DIFFERENT from'} the recorded probes; PROJ still returns 100 m -> 100 m with accuracy -1 (ballpark), SciPy still interpolates across the gap; the T1 package imports none of the probed libraries",
        )

    # TR03 also needs the package validation file
    pv = load(PKG / "PACKAGE_VALIDATION.json")
    if gates["TR03"]["status"] == "pass" and not (pv and pv.get("passed")):
        gates["TR03"].update(status="fail", detail="PACKAGE_VALIDATION.json does not record a pass")
    gates["TR03"]["evidence"].append("handoffs/module-02-terrain/PACKAGE_VALIDATION.json")

    # TD01: GitHub Actions
    ci = load(TERR / "ci-run.json")
    if not ci:
        gate("TD01", "unexecuted", [], "no inspected GitHub Actions run recorded")
    elif ci.get("trees") != trees:
        gate("TD01", "unexecuted", ["reports/terrain/ci-run.json"], f"the inspected run {ci.get('run_url')} tested other source trees than HEAD")
    else:
        jobs_ok = all(j["conclusion"] == "success" for j in ci["jobs"])
        gate_ok = ci.get("evidence_gate", {}).get("passed") is True
        bench_ok = (load(TERR / "ci-benchmark" / "TERRAIN_BENCHMARKS.json") or {}).get("td02", {}).get("pass") is True
        ok = jobs_ok and gate_ok and bench_ok and ci.get("terrain_mcp_steps_ok") is True
        gate("TD01", "pass" if ok else "fail", ["reports/terrain/ci-run.json", "reports/terrain/ci-benchmark/TERRAIN_BENCHMARKS.json", ci["run_url"]], f"run {ci['run_id']} on {ci['head_sha'][:10]}: jobs {[(j['name'], j['conclusion']) for j in ci['jobs']]}; evidence gate passed={gate_ok}; tests {ci.get('evidence_gate', {}).get('tests')}; artifacts {[a['name'] for a in ci['artifacts']]}")

    # TD02: benchmark (local and CI)
    local = load(REPORTS / "TERRAIN_BENCHMARKS.json")
    cib = load(TERR / "ci-benchmark" / "TERRAIN_BENCHMARKS.json")
    if not local or not run_fresh or manifest.get("benchmark_exit") is None:
        gate("TD02", "unexecuted", ["reports/TERRAIN_BENCHMARKS.json"], "no benchmark bound to the current source trees")
    else:
        lt = local["td02"]
        parts = [f"local ({local['machine']['cpu_model']}): placement {lt['process_wall_s']} s, {lt['peak_tree_rss_mib']} MiB, pass={lt['pass']}"]
        ok = lt["pass"]
        if cib and ci and ci.get("trees") == trees:
            ct = cib["td02"]
            parts.append(f"GitHub Actions ({cib['machine']['cpu_model']}): placement {ct['process_wall_s']} s, {ct['peak_tree_rss_mib']} MiB, pass={ct['pass']}")
            ok = ok and ct["pass"]
        else:
            parts.append("no CI benchmark bound to the current trees")
        gate("TD02", "pass" if ok else "fail", ["reports/TERRAIN_BENCHMARKS.json", "reports/terrain/ci-benchmark/TERRAIN_BENCHMARKS.json"], "; ".join(parts) + " (targets 30 s, 1024 MiB)")

    # TD03: fresh clone
    rep = load(TERR / "reproduction" / "reproduction.json")
    if not rep:
        gate("TD03", "unexecuted", [], "no fresh-clone reproduction recorded")
    elif {k: rep["trees"].get(k) for k in rep["trees"]} != {k: trees[k] for k in rep["trees"]}:
        gate("TD03", "unexecuted", ["reports/terrain/reproduction/reproduction.json"], f"the reproduced commit {rep['head'][:10]} has other source trees than HEAD")
    else:
        gate("TD03", "pass" if rep["passed"] else "fail", ["reports/terrain/reproduction/reproduction.json", "reports/terrain/reproduction/reproduction-log.txt"], f"clone of {rep['head'][:10]}: analytic CLI checks {rep['analytic_cli_checks']}; pytest: {rep['steps']['pytest (full suite)']['tail']} (browser required={rep['steps']['pytest (full suite)']['browser_required']})")

    # TD04: delivery report
    dr = ROOT / "TERRAIN_DELIVERY_REPORT.md"
    text = dr.read_text() if dr.is_file() else ""
    needed = ["## Independently verified behaviour", "## Implementation claims", "## Research observations", "## Untested behaviour"]
    gate("TD04", "pass" if all(h in text for h in needed) else ("fail" if text else "unexecuted"), ["solar-site-layout/TERRAIN_DELIVERY_REPORT.md"], "sections present: " + ", ".join(h[3:] for h in needed if h in text))

    for gid in sorted(OUT_OF_SCOPE):
        gate(gid, "unexecuted", [], "out of T1 scope (T2/T3)")

    order = list(TITLES)
    gates = {k: gates[k] for k in order}
    counts: dict[str, int] = {}
    for g in gates.values():
        counts[g["status"]] = counts.get(g["status"], 0) + 1
    in_scope = {k: v for k, v in gates.items() if k not in OUT_OF_SCOPE}
    report = {
        "schema": "solar.terrain.acceptance/1",
        "milestone": "Module 02 T1",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": head,
        "bound_trees": trees,
        "local_run": {"head": manifest.get("head"), "fresh": run_fresh, "pytest_exit": manifest.get("pytest_exit"), "ci_gate_exit": manifest.get("ci_gate_exit"), "tests": (load(RUN / "ci-check.json") or {}).get("tests")},
        "counts": counts,
        "t1_gates_all_pass": all(v["status"] == "pass" for v in in_scope.values()),
        "gates": gates,
    }
    (REPORTS / "TERRAIN_ACCEPTANCE.json").write_text(json.dumps(report, indent=1) + "\n")
    for k, g in gates.items():
        print(f"{k:5} {g['status']:10} {g['detail'][:110]}")
    print(json.dumps(counts))
    return 0 if report["t1_gates_all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
