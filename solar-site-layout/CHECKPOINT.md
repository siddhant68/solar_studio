# Checkpoint

Branch `claude/kind-cerf-gu33em` of `siddhant68/solar_studio`. Pushing from the build session was refused because the GitHub App had no access, so the Git bundle is the off-machine copy.

## Milestones

| # | Commit | What passed | Open items |
|---|---|---|---|
| 1 | `bba6655` | Numerical core: schemas, validation, lattice and phase search, exact borderline checks, verifier. 139 tests: analytic fixtures, 21-pair translation matrix, verifier corruption | — |
| 2 | `3a190c7` | Service, SQLite store, exports, CLI, HTTP, stdio MCP. Plus S01, S03–S07, V04, V05 tests | — |
| 3 | `d7b4f24` | Browser UI and real-browser V01–V03 checks; wire-tapped MCP session (S02); REA execution probe | — |
| 4 | *(this commit)* | Reference evidence and findings, benchmarks, acceptance/packaging scripts, docs | Acceptance run, delivery report, packaging |

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

Next operation after this checkpoint: run the acceptance pipeline on this commit, then write `DELIVERY_REPORT.md`, package, and build `reports/ACCEPTANCE.json`.

The reference build itself is outside this repository and is reproducible from `references/manifest.json` (build recipe and per-file hashes).
