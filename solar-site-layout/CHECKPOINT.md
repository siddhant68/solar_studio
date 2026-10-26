# Checkpoint

Branch `claude/kind-cerf-gu33em` of `siddhant68/solar_studio`. Pushing to this branch works: the original delivery (`f55f4be`) was pushed once access to the GitHub App was granted, and the repair commits below are pushed to the same branch. The earlier note that pushing was blocked is obsolete.

## Milestones

| # | Commit | What passed | Open items |
|---|---|---|---|
| 1 | `bba6655` | Numerical core: schemas, validation, lattice and phase search, exact borderline checks, verifier. 139 tests: analytic fixtures, 21-pair translation matrix, verifier corruption | — |
| 2 | `3a190c7` | Service, SQLite store, exports, CLI, HTTP, stdio MCP. Plus S01, S03–S07, V04, V05 tests | — |
| 3 | `d7b4f24` | Browser UI and real-browser V01–V03 checks; wire-tapped MCP session (S02); REA execution probe | — |
| 4 | `bca0d28` | Reference evidence and findings, benchmarks, acceptance/packaging scripts, docs | — |
| 5 | `f16944e` | First source commit under acceptance: export rebuild fix. 207 tests | Superseded (see 8) |
| 6 | `553b1c1` | Acceptance evidence for `f16944e` | Superseded |
| 7 | `f55f4be` | First delivery: 36/36 recorded as pass, bound to `f16944e` | Superseded: the review found F1–F5 |
| 8 | `b7a3beb` | Independent review (`reviews/module-01/2026-10-26/`) and repair handoff; source unchanged | — |
| 9 | `d935ff2` | Repairs for F1–F5, the browser 404 and the PYTHONHASHSEED-dependent DXF bytes; regressions; pinned browser tooling. Its acceptance run passed 232 tests but failed the D03 timeout demonstration | Timeout fixed in 10 |
| 10 | `fe15c5f` | **Source commit under acceptance**: the generation time limit also covers record construction and verification. (This commit also carries the outputs of the `d935ff2` run, kept as a record.) | — |
| 11 | `4594c5f` | Acceptance evidence for `fe15c5f`: 233 tests passed, 0 skipped; 24/24 browser checks; MCP session and Inspector cross-check; examples; benchmarks | — |
| 12 | *(delivery commit)* | `reports/ACCEPTANCE.json` (36/36 pass, bound to `fe15c5f`), packaging and fresh-clone reproduction of `4594c5f`, delivery report, this checkpoint | Pull request into `main` for review; not merged |

## How to resume

```sh
cd solar-site-layout
uv sync --frozen --python 3.12
scripts/bootstrap_browser.sh                   # pinned Playwright 1.63.0 + Chromium
SOLAR_REQUIRE_BROWSER=1 .venv/bin/python -m pytest -q
.venv/bin/python scripts/run_acceptance.py --inspector-dir <npm dir with @modelcontextprotocol/inspector@2.12.0>
.venv/bin/python scripts/package_delivery.py dist/<name>
.venv/bin/python scripts/build_acceptance_report.py
```

Next operation: review and merge the pull request into `main` (owner decision), and decide the new-code licence (Apache-2.0 is only proposed). Module 02 (terrain) has not been started; its outline is in `DELIVERY_REPORT.md`.

The reference build itself is outside this repository and is reproducible from `references/manifest.json` (build recipe and per-file hashes).
