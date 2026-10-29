# Module 02 T1 checkpoint

**Where the work stands:**
- **Branch:** `feat/module-02-terrain-t1` of `siddhant68/solar_studio`.
- **PR:** [#4](https://github.com/siddhant68/solar_studio/pull/4), based on `claude/kind-cerf-gu33em`, the PR #1 branch.
- **Contents:** the branch also carries PR #2 and PR #3 (combined base `e01e0da`).
- **Merge order:** #1 → #2 → #3 → #4.
- **State:** nothing is merged or tagged, and the licence is undecided.

## Commits

| Commit | Content |
|---|---|
| `e01e0da` | Combined base: PR #2 tip `5a854cc` plus PR #3 tip `3f99509` (`--no-ff` merge) |
| `f276112` | Contracts revision 2, final for T1. Complete schemas, `terrain-policy/1`, performance definition, fixtures T11–T13 |
| `cb091b6` | `solar_terrain` package and the CLI, HTTP and MCP integration |
| `a04a3cb` | 125 terrain tests |
| `3b1d8d1` | CI gate extended to the terrain tests and the terrain MCP evidence; TD02 benchmark job |
| `2dcf16c` | Acceptance runner, report builder and fresh-clone reproduction scripts. These are the **source trees under acceptance** |
| next | Evidence, delivery report and documentation only; the bound trees are unchanged |

## Completed

All of T1 as specified in `handoffs/module-02-terrain/`:
- import of an explicit TIN, with validation and immutable storage;
- frame and vertical reference matched exactly, with no transformations;
- `minimum_clearance_vertical_lift` with clearance over the full footprint;
- exact topological coverage that keeps survey gaps;
- explicit table-local supports, with slope and support-height limits;
- the independent verifier;
- SQLite storage with paging;
- CLI, HTTP and MCP;
- JSON, CSV and supports-CSV exports;
- CI with a benchmark job, and evidence.

The gate results are in `reports/TERRAIN_ACCEPTANCE.json`; the detail is in `TERRAIN_DELIVERY_REPORT.md`.

## Resume

```sh
git clone --branch feat/module-02-terrain-t1 https://github.com/siddhant68/solar_studio && cd solar_studio/solar-site-layout
uv sync --frozen --python 3.12
scripts/bootstrap_browser.sh
SOLAR_REQUIRE_BROWSER=1 .venv/bin/python -m pytest -q          # 360 tests: Module 01 and terrain
.venv/bin/python scripts/run_terrain_acceptance.py               # needs a clean tree; full suite, CI gate and benchmark
.venv/bin/python scripts/terrain_reproduce.py reports/terrain/reproduction   # TD03 from a fresh GitHub clone
.venv/bin/python scripts/build_terrain_acceptance.py             # reports/TERRAIN_ACCEPTANCE.json
(cd ../handoffs/module-02-terrain && ../../solar-site-layout/.venv/bin/python validate_package.py)
```

`reports/terrain/ci-run.json` records an inspected GitHub Actions run, written by hand from the API. To refresh it:
1. Read the latest run of `.github/workflows/module-01.yml` on the branch, with its jobs and artifacts.
2. Download the benchmark artifact into `reports/terrain/ci-benchmark/`, and the main evidence artifact's gate check.
3. Record the run's head commit trees with `git rev-parse <sha>:<path>`.

## Next actions

- Owner review of PR #4, after PRs #1–#3.
- Owner decisions: merge order and merges, the acceptance tag, the licence, and whether T2 starts. T2 would add generated support rows, the DXF/SVG/report exports and a read-only browser view.

## Known failures and open issues

None open at the source commit under acceptance. During development:
- A first verifier version took 22 s on the benchmark. It was vectorized before any evidence was recorded.
- An HTTP body-limit test assumption was corrected.

The gates TC15–TC17, TV04 and TS06 are out of T1 scope and recorded as unexecuted.

## Decisions taken during T1

These are recorded in `handoffs/module-02-terrain/CONTRACTS.md` §10:
- Unreferenced vertices are allowed, but take no part in the surface.
- Decimal thresholds are compared as exact decimal rationals.
- `NaN` in JSON text is `INVALID_INPUT`; through the Python API it is `INVALID_TERRAIN`.
- The HTTP terrain body limit is 256 MiB.
- The time limit also covers imports.
- The verifier assumes a validated stored surface; its arrays' SHA-256 is checked on every load.
- The JSON export embeds `created_at`, while the CSV exports are byte-identical across stores.

**Engineering choices:**
- One MCP server carries the 9 Module 01 tools plus 8 terrain tools.
- Terrain data lives in its own `terrain.sqlite3`.
- The verifier uses a uniform grid, a loose double filter with Fraction fallback, Sutherland–Hodgman clipping and its own boundary rebuild.
- The engine uses an STR-tree, Shewchuk's filter with an exact expansion stage, and GEOS areas.
- In the verifier, module and support records are checked against their schema shapes by direct code for speed; the tests run the JSON Schema validator over every record.
