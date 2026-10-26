# Module 02 acceptance matrix (proposed)

Every gate is recorded as **pass**, **fail**, **blocked** or **unexecuted**, with evidence bound to the source commit by git tree IDs, as in Module 01's `reports/ACCEPTANCE.json`. Missing evidence makes a gate unexecuted, never pass. Expected numbers come from `fixtures/cases/*.json`. They are derived from closed-form formulas and re-derived from the TINs by `fixtures/check_fixtures.py`; neither script is the implementation. Tolerances are 1e-9 m for elevations and areas in analytic fixtures, and 1e-6 m for plan coordinates after rotation.

## Research and contracts (T1)

| Gate | Requirement | Evidence |
|---|---|---|
| TR01 | Sources, commits, licences and authorities recorded; observations of other software kept separate from our results | `research/SOURCES.json`, `RESEARCH.md` |
| TR02 | Library probes re-run against the versions actually locked for T1; any change in vertical-datum, triangulation or no-data behaviour reflected in the contracts | regenerated `library-probes.json` |
| TR03 | Final JSON Schemas versioned and every fixture validated against them; any change to a fixture explained | schema validation log |

## Calculation and contract gates (T1 unless stated)

| Gate | Fixture | Requirement |
|---|---|---|
| TC01 | T08 | Surface validation: missing vertical reference, degenerate, overlapping or clockwise triangles, non-finite z, duplicate plan vertices and a cracked T-junction each return `INVALID_TERRAIN` with the field, and nothing is stored; the consistent T-junction variant is accepted and leaves T03 unchanged |
| TC02 | T08 | `FRAME_MISMATCH`, `DATUM_MISMATCH`, `SOURCE_MISMATCH`, `RESULT_NOT_FOUND`, out-of-footprint supports, a negative clearance and an unsupported policy are rejected with typed errors; **no coordinate or datum transformation is attempted** |
| TC03 | T01 | Planar terrain, six tables, all placed. Lower edges 101.15, 101.30, 101.45, 101.65, 101.80 and 101.95 m; clearance 0.5 m (north-east corner) to 1.0 m (south-west corner); support heights 0.925, 0.625, 0.875 and 0.575 m; slope 6.379370 deg; 24 modules, 13.2 kWp placed |
| TC04 | T02 | 3-4-5 table on ground rising at 0.25. L = 51.0 m and upper edge 54.0 m (lift +50.2 m); clearance 0.5 m (front) to 2.5 m (rear); supports 0.75 m (d = 0.5) and 2.25 m (d = 3.5); slope 14.036243 deg |
| TC05 | T03 | **Full-footprint clearance.** The hill top (4, 4, 10.6) inside the footprint governs: L = 11.1 m; minimum clearance 0.5 m at (4, 4); corners 0.8 m. The corner-only answer of 10.8 m must not be produced |
| TC06 | T04 | **Void under a rack.** All corners are surveyed but 1.0 m² of the footprint is not: `unknown_ground`, covered 7.0 m², uncovered 1.0 m²; no elevation, modules or supports; never placed at 10.5 m |
| TC07 | T05 | **Partial survey.** Tables at x ∈ [4, 6], ending on the survey edge, are placed; tables at x ∈ [7, 9] are `unknown_ground` (8 m² uncovered each); 16 modules and 8.8 kWp placed; nothing extrapolated |
| TC08 | T06 | Support-height limit: L = 23.5 m, front supports 1.4 m > 1.2 m → `infeasible` (`support_above_ground_exceeds_limit`); elevations still reported; 0 placed |
| TC09 | T07 | Slope limit: atan(0.6) = 30.963757 deg > 25 deg → `infeasible` (`ground_slope_exceeds_limit`) |
| TC10 | T09 | **Translated/rotated survey frame.** The T03 problem rotated 30 deg CCW and moved into EPSG:32633 gives the same IDs, statuses, elevations, clearances and support heights (1e-9 m); plan coordinates are the transformed T03 coordinates (1e-6 m) |
| TC11 | all | Elevations are in the terrain's vertical reference with `z_kind = terrain_vertical_reference`; `not_computed` lists embedment depth, pile length, foundation design, structural adequacy, grading, cut/fill and drainage; no output calls a support height a pile length |
| TC12 | T01, T03 | The Module 01 source result, its payload digest and every issued Module 01 export are byte-identical before and after placement |
| TC13 | — | Identity: equivalent requests (int vs float, re-ordered keys, renamed surface) give the same `terrain_id` and `placement_id`; any change to geometry, datum, parameters or source changes them |
| TC14 | — | Limits: vertex, triangle and coordinate limits and a finite timeout return typed `RESOURCE_LIMIT` before unbounded work, and nothing is stored |
| TC15 (T2) | — | `uniform_rows` support generation reproduces a hand-listed position set; the count follows the stated model, not module count |
| TC16 (T3) | new | DEM adapter: masked no-data blocks produce no triangles; pixel-centre registration matches GDAL for GeoTIFF (Area and Point) and ESRI ASCII XLLCENTER/XLLCORNER; a void cell under a table gives `unknown_ground` |
| TC17 (T3) | new | LandXML TIN import gives the same `terrain_digest` as the equivalent JSON surface |

## Verifier and exports

| Gate | Requirement |
|---|---|
| TV01 | The independent verifier passes every placement fixture result and is not implemented by calling the engine |
| TV02 | It rejects every corruption in T10: lowered tables, a shifted module corner, a misreported clearance, an unknown-ground table reported as placed, a wrong support height, a replaced source digest, a shifted footprint, inconsistent totals, a changed datum, and an over-lifted table |
| TV03 | JSON/CSV exports round-trip every record exactly; write-once and context-file rules as in Module 01 |
| TV04 (T2) | DXF/SVG/report match the records; the report states the policy, datum and `not_computed` list |

## Service and interfaces

| Gate | Requirement |
|---|---|
| TS01 | CLI, HTTP and MCP give the same terrain and placement identities and the same typed errors |
| TS02 | Paging of tables, modules and supports is bounded and stable, with typed invalid-cursor errors; summary reads do not load records |
| TS03 | Restart reads everything back; an interrupted import or placement leaves no partial result |
| TS04 | Provenance records the algorithm and policy versions, source commit and dependency versions |
| TS05 | A real MCP client session covers import, place, page, export and a typed datum-mismatch error, with the wire transcript kept |
| TS06 (T2) | Real-browser check of the read-only placement view, with no console errors, failed requests or HTTP errors |

## Delivery

| Gate | Requirement |
|---|---|
| TD01 | GitHub Actions runs the Module 01 and Module 02 suites with browser and MCP tests required; the run and artifact URLs are recorded |
| TD02 | Benchmark: the 10,192-module Module 01 benchmark layout placed on a 500,000-triangle TIN covering it in ≤ 30 s with ≤ 1 GiB peak process-tree memory on the CI runner class (proposed target) |
| TD03 | Fresh clone, locked install, analytic CLI workflow and full tests reproduce |
| TD04 | The delivery report separates verified behaviour, reference observations, assumptions, untested platforms and remaining failures |
