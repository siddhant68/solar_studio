# Delivery report: Solar Studio Module 02, milestone T1 (terrain placement by vertical lift)

**Source under acceptance:** `2dcf16c77415ead29fb97bc698a928e398e6de0a` on branch `feat/module-02-terrain-t1`. The PR is [#4](https://github.com/siddhant68/solar_studio/pull/4), based on `claude/kind-cerf-gu33em`.

`reports/TERRAIN_ACCEPTANCE.json` binds every gate to that commit by the git tree IDs of:
- `solar-site-layout/src`, `tests`, `scripts`, `pyproject.toml`, `uv.lock` and `fixtures`;
- `handoffs/module-02-terrain/contracts` and `fixtures`;
- `.github`.

The commit after it adds only evidence, reports and documentation, so the trees are unchanged.

**Summary.**
- **Scope:** T1 is implemented as specified and stops at its acceptance boundary. Nothing from T2–T4 was built.
- **Gates:** all 33 in-scope T1 gates pass (TR01–TR03, TC01–TC14, TC18–TC21, TV01–TV03, TS01–TS05, TD01–TD04). The five T2/T3 gates (TC15–TC17, TV04, TS06) are recorded as *unexecuted (out of T1 scope)*.
- **Tests:** 360 passed, none failed or skipped: 125 terrain tests and Module 01's 235, with the real browser required.
- **CI:** the GitHub Actions run passed, including a new benchmark job.
- **Reproduction:** a fresh clone with a locked install reproduces the CLI workflow and the full suite.
- **TD02:** placement of 10,192 modules on 500,000 triangles takes 6.4 s (GitHub runner) to 7.8 s (this container) of process wall time. Peak process-tree memory is 338–343 MiB, against targets of 30 s and 1 GiB.
- **Review status:** no independent reviewer has examined T1 yet; see "What 'independent' means here".
- **Not done:** nothing is merged or tagged, and the licence is undecided.

## Branch, commits and pull requests

**Branch and PR.**
- Branch: `feat/module-02-terrain-t1`.
- PR: https://github.com/siddhant68/solar_studio/pull/4 (base `claude/kind-cerf-gu33em`).
- It depends on [PR #1](https://github.com/siddhant68/solar_studio/pull/1) (Module 01), and contains [PR #2](https://github.com/siddhant68/solar_studio/pull/2) (`5a854cc`, CI and the browser-enforcement fix) and [PR #3](https://github.com/siddhant68/solar_studio/pull/3) (`3f99509`, the terrain proposal).
- Proposed merge order: #1 → #2 → #3 → #4. The Module 01 acceptance tag should include PR #2's browser fix.

| Commit | Content |
|---|---|
| `e01e0da` | Combined base: PR #2 tip with PR #3 merged (`--no-ff`); no other change |
| `f276112` | **Contracts revision 2** (a separate commit, before any code). Complete result schema with status-dependent records; complete `expected_vertical`; exact numerical policy `terrain-policy/1`; performance definition; fixtures T11–T13 |
| `cb091b6` | `solar_terrain` package; new error codes; CLI, HTTP and MCP integration |
| `a04a3cb` | 125 terrain tests |
| `3b1d8d1` | CI gate extended to the terrain tests and the terrain MCP evidence; TD02 benchmark job |
| `2dcf16c` | Acceptance runner, report builder, fresh-clone reproduction. **Source under acceptance** |
| next | Evidence, reports and documentation (`CONTRACTS.md` §10 clarifications, READMEs, this report, checkpoint) |

## Acceptance matrix

The full record, with evidence paths and details, is `reports/TERRAIN_ACCEPTANCE.json`; it is built by `scripts/build_terrain_acceptance.py`. "Tests" means JUnit cases from the local acceptance run (`reports/terrain/acceptance-run/`), all of which also passed in CI.

| Gate | Status | Evidence |
|---|---|---|
| TR01 sources and authorities | pass | `handoffs/module-02-terrain/research/SOURCES.json`, `RESEARCH.md` |
| TR02 probes re-run | pass | `reports/terrain/library-probes-rerun.json`, byte-identical to `research/library-probes.json` (pyproj 3.7.2/PROJ 9.5.1, SciPy 1.16.2, rasterio 1.4.3/GDAL 3.9.3) |
| TR03 contract package | pass | `test_terrain_contracts.py` (8); `handoffs/module-02-terrain/PACKAGE_VALIDATION.json` |
| TC01 invalid surfaces | pass | `test_terrain_errors.py::test_tc01_*` (14) |
| TC02 typed request errors, no transformation | pass | `test_terrain_errors.py::test_tc02_*` (21) |
| TC03–TC09 fixtures T01–T07 | pass | `test_terrain_fixtures.py::test_fixture_case_values[T0x]`, `test_tc05_*` |
| TC10 rotated/translated frame | pass | `test_tc10_rotated_and_translated_frame` |
| TC11 `z_kind`, `not_computed`, no pile fields | pass | `test_tc20_tc11_*` (10) |
| TC12 Module 01 unchanged | pass | `test_terrain_service.py::test_tc12_*` (T01, T03) |
| TC13 identities | pass | `test_tc13_*`, `test_terrain_ids_equal_the_fixture_index` |
| TC14 limits | pass | `test_tc14_*` (4), `test_http_terrain_body_limit` |
| TC18 micro-gap | pass | `[T11]`, `test_tc18_*` |
| TC19 T-junctions | pass | `[T12]`, `test_tc19_*`, `test_tc01_cracked_t_junction_*` |
| TC20 status-dependent records | pass | `test_tc20_tc11_*` (full JSON Schema validation of every record), all fixture cases |
| TC21 exact support tie | pass | `[T13]`, `test_tc21_*` |
| TV01 verifier independence and bounded candidates | pass | `test_tv01_*`, `test_import_boundary`, `test_verifier_does_not_call_the_engine`, `test_terrain_predicates.py` |
| TV02 T10 corruptions | pass | `test_tv02_*` (10), `test_verification_failure_stores_nothing` |
| TV03 exports | pass | `test_tv03_*` (3) |
| TS01 interface parity | pass | `test_ts01_*` |
| TS02 paging | pass | `test_ts02_*` (2) |
| TS03 restart and crashes | pass | `test_ts03_*` (7: restart; SIGKILL at 3 import and 3 placement fault points) |
| TS04 provenance | pass | `test_ts04_*` |
| TS05 real MCP session | pass | `test_ts05_*`; `reports/terrain/acceptance-run/terrain-mcp/` (20 steps, 41 wire messages) |
| TD01 GitHub Actions | pass | [run 40928517340](https://github.com/siddhant68/solar_studio/actions/runs/40928517340); `reports/terrain/ci-run.json` |
| TD02 benchmark | pass | `reports/TERRAIN_BENCHMARKS.json` (local), `reports/terrain/ci-benchmark/` (CI) |
| TD03 fresh clone | pass | `reports/terrain/reproduction/` |
| TD04 this report | pass | this file |
| TC15–TC17, TV04, TS06 | unexecuted (out of T1 scope) | T2/T3 |

## CI run and artifacts

[Run 40928517340](https://github.com/siddhant68/solar_studio/actions/runs/40928517340) tested `pull_request` at head `2dcf16c`. GitHub checked out the merge commit `e194fb2`, whose root tree equals `2dcf16c`'s. Both jobs succeeded:

- **Full suite (Linux, Python 3.12, Chromium required):** 360/360 passed. The evidence gate passed with 24 browser checks, 17 MCP steps and 20 terrain MCP steps. Artifact [`module-01-evidence-run40928517340-attempt1`](https://github.com/siddhant68/solar_studio/actions/runs/40928517340/artifacts/12920739475): 2,209,682 bytes, sha256 `3c8800c9…bdb`.
- **Terrain benchmark TD02:** pass. Artifact [`terrain-benchmark-run40928517340-attempt1`](https://github.com/siddhant68/solar_studio/actions/runs/40928517340/artifacts/12922150889): sha256 `f68f91b3…060f`.

Both artifacts were downloaded and their SHA-256 matched GitHub's digests. Their small files are kept in `reports/terrain/ci-evidence/` and `reports/terrain/ci-benchmark/`. The artifacts expire on 28 November 2026. An earlier run, [40927836400](https://github.com/siddhant68/solar_studio/actions/runs/40927836400) on `3b1d8d1`, also passed with the same source and tests.

## Benchmarks (TD02, `PLAN.md` §11)

**Construction:**
- **Layout:** Module 01 `fixtures/benchmark-10k.request.json`, with 10,192 modules in 364 tables.
- **Terrain:** a 501 × 501 grid with 500,000 triangles over the site's bounding box plus 10 m, with cells of 0.67 × 0.38 m, and z = 100 + 0.02x′ + 0.03y′ + 0.4 sin(x′/9) cos(y′/13).
- **Placement:** 6 supports per table; all 364 tables placed and verified.

Each phase ran in a fresh process. Process-tree RSS was sampled every 10 ms, and wall time includes interpreter start.

| Phase | This container (Intel Xeon 2.10 GHz, 4 vCPU, 16 GB) | GitHub Actions (AMD EPYC 9V74, 4 vCPU, 16 GB) | Target |
|---|---|---|---|
| **Placement (TD02)**: verification and persistence included, prepared terrain stored | **7.78 s, 338.3 MiB** | **6.38 s, 342.5 MiB** | ≤ 30 s, ≤ 1024 MiB: **pass** |
| of which: engine / independent verifier / persistence | 3.60 / 3.08 / 0.20 s | 3.03 / 2.50 / 0.20 s | — |
| Terrain import (24.7 MB JSON on disk → validated, prepared, stored) | 12.08 s, 599.3 MiB | 7.00 s, 602.9 MiB | reported only |
| Cold workflow (layout + import + placement, one process) | 20.37 s, 603.0 MiB | 14.18 s, 608.8 MiB | reported only |

Run 40927836400 (`3b1d8d1`) measured 7.70 s / 342.1 MiB for placement on the runner.

**Failure during development.** The first verifier was profiled in-process before any evidence was recorded. It took 22 s of a 28 s placement, spent mostly in per-triangle slope checks and JSON Schema validation of every module record. It was vectorized before the evidence runs. Module and support records are now checked against their schema shapes by direct code at runtime, and the tests still run the JSON Schema validator over every record. No benchmark failed against the target.

## Fresh-clone reproduction (TD03)

`scripts/terrain_reproduce.py` cloned `feat/module-02-terrain-t1` at `2dcf16c` from GitHub into an empty directory. It then ran:
1. `uv sync --frozen` with an empty uv cache (16 s);
2. the pinned browser bootstrap;
3. the analytic CLI workflow for T01, T03 and T04 (import, place, items, three exports, verify), with expected numbers checked;
4. the full suite with the browser required: **360 passed**.

The evidence is in `reports/terrain/reproduction/`. To reproduce by hand:

```sh
git clone --branch feat/module-02-terrain-t1 https://github.com/siddhant68/solar_studio && cd solar_studio/solar-site-layout
UV_CACHE_DIR=$(mktemp -d) uv sync --frozen --python 3.12
scripts/bootstrap_browser.sh
F=../handoffs/module-02-terrain/fixtures
.venv/bin/solar-layout --data-dir /tmp/d generate $F/layouts/single-flat-4x2.layout-request.json
.venv/bin/solar-layout --data-dir /tmp/d terrain import $F/surfaces/hill-fan.surface.json
python3 -c "import json;print(json.dumps(json.load(open('$F/cases/T03.json'))['placement_request']))" > /tmp/t03.json
.venv/bin/solar-layout --data-dir /tmp/d terrain place /tmp/t03.json        # tables: L = 11.1 m, min clearance 0.5 m at (4, 4)
SOLAR_REQUIRE_BROWSER=1 .venv/bin/python -m pytest -q                      # 360 passed
.venv/bin/python scripts/terrain_benchmark.py /tmp/TERRAIN_BENCHMARKS.json  # TD02
```

## What "independent" means here

The engine, the verifier and the tests were written by the same agent, in the same session, from the same contracts. The verifier is independent in code:
- it imports no engine, predicate or surface module (enforced by an AST test, and checked at runtime by disabling every engine entry point);
- it reaches each conclusion by a different route.

It is not independent in authorship, so a shared misreading of the contracts would not be caught by it. The independent oracles are:
- the fixture expectations, derived from closed forms by `make_fixtures.py` and re-derived from the TINs by `check_fixtures.py`, both written before the implementation;
- the Module 01 results the fixtures start from;
- GitHub's runner.

No human or separate agent has reviewed T1.

## Independently verified behaviour

Checked against oracles the implementation does not produce: the closed-form fixtures, the independent checker, Module 01's stored records, and a second process or machine.

- **Elevations match the closed-form values within 1e-9 m:**
  - T01 planar: six tables, lower edges 101.15–101.95 m, supports 0.925/0.625/0.875/0.575 m, slope 6.379370°.
  - T02 tilted 3-4-5: L 51.0 m, upper 54.0 m, lift 50.2 m.
  - T03 interior hill: L 11.1 m, minimum clearance 0.5 m at (4, 4). The corner-only 10.8 m is not produced.
  - T13: a support exactly at the 1.25 m limit is placed; with a limit 1e-10 m lower the table is infeasible.
- **Coverage, decided exactly:**
  - T04 void: 7.0/1.0 m², unknown ground although all corners are surveyed.
  - T05 survey edge on table edges: covered.
  - T11 micro-gap: a 0.000001 m strip is unknown ground, with an uncovered area within 1e-12 m² of 2 × (4.000001 − 4).
  - T12 T-junction: accepted, and gives the T03 result.
- **Limits:** T06 support limit and T07 slope limit make tables infeasible, keeping their elevations and supports, without modules or capacity.
- **Frame independence:** T09, rotated 30° and moved into EPSG:32633, gives the same IDs and elevations within 1e-9 m and plan coordinates within 1e-6 m.
- **Identity:** every terrain ID and digest equals the fixture index computed by the generator. Fixture regeneration is byte-identical, and the independent checker passes.
- **Module 01 unchanged (TC12):** before and after import, placement, terrain exports and re-verification, the same result rows, summaries, records and export files (path, SHA-256, inode, bytes).
- **Second process or machine:**
  - CLI, HTTP and MCP give identical placement IDs and payload digests, and the same `DATUM_MISMATCH` / `TERRAIN_NOT_FOUND` codes.
  - A process killed at six write points leaves no rows.
  - Exports are byte-identical across processes and hash seeds.
  - A fresh clone and a GitHub runner reproduce the suite.
  - The probes re-run identically.

## Implementation claims

Asserted by design and exercised by tests, but not proven in general:

- **Exactness.** Orientation, containment, overlap, crossing, coverage and point location are exact for every input: Shewchuk's filter, then an exact expansion stage, then `Fraction`. The predicates are compared with rational arithmetic on about 24,000 orientation cases and about 2,900 segment cases and agree on all of them. The orientation cases are sampled from 140,000 adversarial inputs: near-collinear at magnitudes up to 1e7, and exactly collinear dyadic points. This is a sample.
- **Verifier coverage.** It re-derives each check by a different route:
  - its own uniform grid, a loose double filter with `Fraction`, Sutherland–Hodgman clipping and its own boundary rebuild;
  - the engine instead uses an STR-tree, prepared boundary segments and GEOS areas.

  It rejects all ten T10 corruptions with the named checks. Corruptions outside that list are not demonstrated.
- **Minimum lift.** The overlay-point maximum gives the exact minimum lift; the verifier's clipping route agrees within 1e-9 m on every fixture and on the 364 benchmark tables.
- **Bounded candidates.** Candidates are bounded per table in both engine and verifier: on an 80,000-triangle grid each examined at most 48 triangles per 2 × 4 m table (the test allows 60); on the 500,000-triangle benchmark, at most 624 (engine) and 832 (verifier) for a table of about 16 × 4 m.
- **Concurrency.** Imports and placements are each one SQLite `BEGIN IMMEDIATE` transaction, with an existence check inside it. Export publication follows Module 01's repaired, concurrency-tested design (unique staging, thread lock and `flock`, re-hash on reuse). For terrain, crash safety, write-once reuse, tamper restore and cross-process rebuilds are tested; truly simultaneous writers are not.
- **Identity.** `terrain_digest` is streamed, and is byte-identical to Module 01's canonical JSON of the identity body (tested on a fixture).

## Research observations

These are observations of other software, kept separate from our results. Sources and authorities are in `handoffs/module-02-terrain/research/SOURCES.json`.

**Re-run here on 29 October 2026 with the recorded versions, with identical output:**
- Offline, without the geoid grid, PROJ 9.5.1 turns WGS 84 ellipsoidal height into EGM96 height with a ballpark no-op (100 m in, 100 m out, accuracy −1). It gives no error, even with `only_best`. This is why T1 performs no vertical transformation.
- SciPy `Delaunay` with `LinearNDInterpolator` triangulates across an unsurveyed gap and returns a finite value there. This is why T1 accepts only explicit TINs and keeps gaps.
- With GDAL/rasterio, unmasked sampling returns the raw no-data value. This matters for the T3 DEM adapter.

**Read from source (PVPlant at `7852ee5`, not run):** the mesh keeps zero-initialized degenerate triangles; XLLCENTER handling is wrong; no-data is scaled before comparison; and terrain adjustment samples only the table's centre line. The T03 and T04 fixtures cover that last failure mode.

T1 imports none of these libraries; a test checks this.

## Untested behaviour

- **Platforms:** tested only on Linux x86_64 with Python 3.12.3 (container and GitHub's ubuntu-24.04). macOS, Windows (the fault injection uses POSIX signals) and Python 3.13+ are untested.
- **Real data:** surfaces are synthetic and analytic. No real survey TIN, slivers from real triangulations, or LandXML/DEM-derived surfaces have been tried.
- **Size limits:** surfaces at the T1 limits (1,000,000 vertices, 2,000,000 triangles) were not run. A 500,000-triangle import peaks at about 600 MiB, so a 2,000,000-triangle import may need several GiB; there is no import target in T1. The HTTP terrain body limit (256 MiB) was tested only with a lowered limit.
- **MCP size:** MCP carries surfaces inline; only small fixture surfaces were sent over MCP.
- **Concurrency:** two processes placing the identical request at the same moment, and simultaneous terrain export writers.
- **Slope threshold:** a limit whose tan(limit) is within a few ulps of a triangle's gradient can decide differently with a different libm (stated in `CONTRACTS.md` §4.4). It is not tested across platforms.
- **Out of scope:** everything in T2–T4: generated support rows, DXF/SVG/report exports, a browser view, DEM/LandXML adapters, reorientation, grading, drainage, foundations and piles.

## Limitations

- **Placement policy:** vertical lift only. Tables keep Module 01's tilt and plan geometry; they never follow the ground (T4).
- **Supports:** only the stated table-local points. Above-ground height is not embedment depth or pile length. Every result lists `not_computed`: embedment depth, pile length, foundation design, structural adequacy, grading, cut/fill and drainage.
- **Coverage:** a survey gap of any width makes a table `unknown_ground`; there is no interpolation and no partial placement.
- **Areas:** covered and uncovered areas are informative double sums, not decisions.
- **JSON export timestamp:** the JSON export embeds `provenance.created_at`, so two independent stores differ in that field only. The CSV exports are byte-identical everywhere.
- **Assumption on stored surfaces:** the verifier relies on the stored surface having passed import validation; arrays are SHA-256-checked on every load.
- **Clarifications** made during implementation (unreferenced vertices, decimal thresholds, `NaN` parsing, body limit and others) are recorded in `handoffs/module-02-terrain/CONTRACTS.md` §10.

## Owner decisions

The owner's instruction did not authorize any of these, so none was taken:
1. **Merges:** PR #1, then #2, then #3, then #4. While #1–#3 are open, #4 shows their changes too.
2. **Acceptance tag** for the Module 01 checkpoint, including PR #2's browser fix.
3. **Licence** for the new code (Apache-2.0 is proposed only).
4. **Whether T2 starts:** generated support rows, DXF/SVG/report exports and a read-only browser view.
5. **Optional:**
   - whether the T1 count limits (1 M vertices / 2 M triangles) should stay without an import memory target;
   - whether the terrain tools should stay on the same MCP server as Module 01 (they do now, with 17 tools).
