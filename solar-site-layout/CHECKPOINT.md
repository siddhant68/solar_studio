# Checkpoint

Branch `claude/kind-cerf-gu33em` of `siddhant68/solar_studio`. Pushing from the build session was refused because the GitHub App had no access, so the Git bundle is the off-machine copy.

## Milestones

| # | Commit | What passed | Open items |
|---|---|---|---|
| 1 | `bba6655` | Numerical core: schemas, validation, lattice and phase search, exact borderline checks, verifier. 139 tests: analytic fixtures, 21-pair translation matrix, verifier corruption | — |
| 2 | `3a190c7` | Service, SQLite store, exports, CLI, HTTP, stdio MCP. Plus S01, S03–S07, V04, V05 tests | — |
| 3 | `d7b4f24` | Browser UI and real-browser V01–V03 checks; wire-tapped MCP session (S02); REA execution probe | — |
| 4 | `bca0d28` | Reference evidence and findings, benchmarks, acceptance/packaging scripts, docs | — |
| 5 | `f16944e` | **Source commit under acceptance**: export rebuild fix. 207 tests pass, including real browser and MCP | — |
| 6 | `553b1c1` | Acceptance evidence (tests, browser, MCP, examples, benchmarks, Inspector cross-check) | — |
| 7 | *(delivery commit)* | Packaging and fresh-clone reproduction evidence, `reports/ACCEPTANCE.json` (36/36 pass, bound to `f16944e` tree IDs), delivery report | Push to GitHub (no App access from the build session) |

The reference investigation (REA static plus runtime, Playwright, PVPlant source reading) ran before and alongside milestone 1. Its evidence is committed in milestone 4.

## How to resume

```sh
cd solar-site-layout
uv sync --frozen --python 3.12
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_acceptance.py --inspector-dir <inspector npm dir>
.venv/bin/python scripts/package_delivery.py ../dist
.venv/bin/python scripts/build_acceptance_report.py
```

Next operation: review the delivery, push the bundle's branch to GitHub from a machine with access (`git clone solar_studio-<sha>.bundle && git push origin claude/kind-cerf-gu33em`), and decide the new-code licence. Then start Module 02 (terrain) as outlined in `DELIVERY_REPORT.md`.

The reference build itself is outside this repository and is reproducible from `references/manifest.json` (build recipe and per-file hashes).
