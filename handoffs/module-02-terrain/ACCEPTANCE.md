# Module 02 acceptance matrix (revision 2, T1)

Every gate is recorded as **pass**, **fail**, **blocked** or **unexecuted**, with evidence bound to the source commit by git tree IDs. The recorded file is `solar-site-layout/reports/TERRAIN_ACCEPTANCE.json`, built by `scripts/build_terrain_acceptance.py`. Missing evidence makes a gate unexecuted, never pass.

Expected numbers come from `fixtures/cases/*.json`. They are derived from closed forms by `make_fixtures.py` and re-derived from the TINs by `check_fixtures.py`. Neither script is the implementation.

Tolerances:
- elevations, clearances and support heights: 1e-9 m;
- areas: 1e-9 · max(1, area) m²;
- plan coordinates after rotation: 1e-6 m;
- the micro-gap's uncovered area: 1e-12 m².

Coverage, point location and the support-height limit are decided exactly (`CONTRACTS.md` §4).

## Research and contracts

| Gate | Requirement | Evidence |
|---|---|---|
| TR01 | Sources, commits, licences and authorities recorded; observations of other software kept separate from our results | `research/SOURCES.json`, `RESEARCH.md` |
| TR02 | Library probes re-run with the recorded versions. T1 depends on none of the probed libraries (pyproj, SciPy, rasterio); the re-run confirms the behaviours behind the contract decisions (silent ballpark vertical transformation; gap-filling triangulation). A changed outcome triggers contract review | regenerated `library-probes.json` |
| TR03 | Final schemas valid (draft 2020-12). Every fixture surface and request validates. Fixture regeneration is byte-identical. The independent checker passes. Every terrain ID in `surfaces/INDEX.json` equals the implementation's | `PACKAGE_VALIDATION.json`, tests |

## Calculation and contract gates

| Gate | Fixture | Requirement |
|---|---|---|
| TC01 | T08, surfaces | Surface validation returns `INVALID_TERRAIN` with the field, and nothing is stored, for: missing vertical reference, degenerate/overlapping/clockwise triangles, non-finite z, duplicate plan vertices, a **cracked T-junction**. Out-of-envelope coordinates or z, and too many triangles, return `RESOURCE_LIMIT` |
| TC02 | T08 | Typed errors with nothing stored: `FRAME_MISMATCH`; `DATUM_MISMATCH` (CRS and local-benchmark mismatch); `INVALID_INPUT` for an empty or partial `expected_vertical`, a support outside the footprint and a negative clearance; `SOURCE_MISMATCH`; `RESULT_NOT_FOUND`; `TERRAIN_NOT_FOUND`; `UNSUPPORTED_OPERATION` (policy, support model). A matching `expected_vertical` is accepted. No coordinate or datum transformation is attempted anywhere |
| TC03 | T01 | Planar terrain, six tables, all placed. Lower edges 101.15/101.30/101.45/101.65/101.80/101.95 m; clearance 0.5–1.0 m; support heights 0.925, 0.625, 0.875, 0.575 m; slope 6.379370°; 24 modules and 13.2 kWp placed |
| TC04 | T02 | Tilted 3-4-5 table: L = 51.0 m, upper edge 54.0 m, lift +50.2 m; clearance 0.5–2.5 m; supports 0.75/2.25 m; slope 14.036243° |
| TC05 | T03 | Interior hill: L = 11.1 m; minimum clearance 0.5 m at (4, 4); corner clearance 0.8 m. The corner-only value 10.8 m is not produced |
| TC06 | T04 | Void under the middle with surveyed corners: `unknown_ground`; covered 7.0 m², uncovered 1.0 m²; no elevations, modules or supports |
| TC07 | T05 | Survey edge exactly on table edges: those tables are covered and placed; tables beyond are `unknown_ground` (8 m² each); 16 modules and 8.8 kWp placed |
| TC08 | T06 | Support-height limit: `infeasible`; elevations and supports retained; excluded from placed counts |
| TC09 | T07 | Slope limit: `infeasible` (`ground_slope_exceeds_limit`) |
| TC10 | T09 | Rotated 30° and moved into EPSG:32633: the same IDs, statuses, elevations, clearances and support heights as T03 (1e-9 m); plan coordinates transformed (1e-6 m) |
| TC11 | all | `z_kind = terrain_vertical_reference`; `not_computed` is exactly the seven-item list; no field or text calls a support height a pile length or an embedment depth |
| TC12 | T01, T03 | The Module 01 source result, its payload digest and every issued Module 01 export are byte-identical (same path, bytes and inode) before and after terrain import and placement |
| TC13 | all | Identities: equivalent surfaces (int vs float, key order, renamed) and requests give the same `terrain_id` and `placement_id`, equal to the fixture index. Changing geometry, datum, parameters or source changes them. Repeating an import or placement reuses the stored row |
| TC14 | — | Limits: vertex/triangle counts, coordinate envelope and a finite placement time limit return typed `RESOURCE_LIMIT` before unbounded work, and nothing is stored |
| TC18 | T11 | **Micro-gap.** A 0.000001 m strip under a table whose four corners are surveyed: `unknown_ground`, uncovered area 2 × (double(4.000001) − 4) m² (1e-12 m²) |
| TC19 | T12, T08 | **T-junctions.** The consistent T-junction surface is accepted and gives the T03 placement (L = 11.1 m); the cracked one is rejected (TC01) |
| TC20 | all | **Status-dependent records.** Every result validates against the final result schema. `unknown_ground` tables have no elevation fields and no module or support records. `infeasible` tables keep elevations, reasons and supports but no modules, and are excluded from placed counts and capacity. The verifier checks the count relations |
| TC21 | T13 | **Exact support-limit tie.** A support exactly at the limit (1.25 m) is within it, and the table is placed. A limit 1e-10 m lower makes it `infeasible`. Both decided by the exact band |

## Verifier and exports

| Gate | Requirement |
|---|---|
| TV01 | The independent verifier passes every fixture placement. It shares no geometry code with the engine (import-boundary test) and uses its own bounded candidate selection. Its own candidate counts are reported |
| TV02 | It rejects every T10 corruption, naming the failing check: a lowered table, a shifted module corner, a misreported clearance, an unknown-ground table reported as placed, a wrong support height, a replaced source digest, a shifted footprint, inconsistent totals, a changed datum, an over-lifted table |
| TV03 | JSON/CSV/supports CSV exports round-trip every record exactly. They are write-once (repeat = same inode; a tampered file is restored with identical bytes) and byte-identical across processes and hash seeds |

## Service and interfaces

| Gate | Requirement |
|---|---|
| TS01 | CLI, HTTP and MCP give the same terrain and placement identities and the same typed errors |
| TS02 | Paging of tables, modules and supports is bounded and stable, with typed invalid-cursor errors; summary reads do not load records |
| TS03 | Restart reads everything back. A process killed during terrain import or placement (fault points) leaves no terrain or placement row and no partial records, and the same request then succeeds |
| TS04 | Provenance records the algorithm and policy versions, source commit and dependency versions |
| TS05 | A real MCP client session covers import, place, paging, export and a typed `DATUM_MISMATCH`, with the wire transcript kept |

## Delivery

| Gate | Requirement |
|---|---|
| TD01 | GitHub Actions runs the full suite: Module 01 with browser and MCP required, plus terrain. The gate also requires the terrain MCP evidence, and the benchmark job uploads its report. Run and artifact URLs are recorded |
| TD02 | Benchmark as defined in `PLAN.md` §11: **placement (including independent verification and persistence, prepared terrain stored) ≤ 30 s process wall time and ≤ 1 GiB peak process-tree memory**. Import and the cold workflow are reported separately. Hardware and versions are recorded. A miss is a fail |
| TD03 | A fresh clone with a locked install runs the analytic CLI workflow and the full test suite |
| TD04 | The delivery report separates independently verified behaviour, implementation claims, research observations and untested behaviour |

## Not part of T1

TC15 (generated support rows), TC16–TC17 (DEM, LandXML), TV04 (DXF/SVG/report) and TS06 (browser view) belong to T2/T3. They are recorded as *unexecuted (out of T1 scope)*.

## Changes from revision 1

- **Tightened:**
  - TR02: the probed libraries are not T1 dependencies.
  - TR03: terrain IDs must equal the fixture index.
  - TC01/TC02: T-junction files, the `expected_vertical` rules, `RESOURCE_LIMIT` for the envelope, and `TERRAIN_NOT_FOUND`.
  - TC13: equality with the fixture index.
  - TV01: no shared geometry code, and bounded candidates.
  - TV03: tamper restore and cross-process determinism.
  - TS03: fault points.
  - TD01: terrain MCP evidence and the benchmark job.
  - TD02: the measurement definition.
- **Added:** TC18 micro-gap, TC19 T-junctions, TC20 status-dependent records and TC21 exact limit tie.
