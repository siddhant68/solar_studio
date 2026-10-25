# Acceptance matrix — Module 01

All gates below are mandatory for a complete delivery. Mark pass, fail, blocked or unexecuted individually, with source commit, exact command and evidence path. Test count is informational. A partial delivery is useful but must not be labelled complete.

## Reference and REA evidence

| Gate | Acceptance |
|---|---|
| R01 | Reference commit/build, file hashes, runtime and licence findings are recorded; any reference substitution has a stated reason. |
| R02 | A real REA JavaScript analysis of the selected built reference artifact is retained and parseable; source-only reading or our own new app cannot substitute for this gate. |
| R03 | At least three repeatable local reference scenarios are executed: small array, a changed geometry control, and save/reload. Each has inputs, outcomes, screenshots/state and honest REA-versus-Playwright attribution. |
| R04 | At least two reference findings affect a documented implementation decision; JS/WASM coverage limitations are explicit. |

## Input and mathematical core

| Gate | Acceptance |
|---|---|
| C01 | Versioned schemas reject missing units/frames, NaN/Inf, degenerate/self-crossing rings, bad holes and unsupported degree/Z inputs with typed field errors. |
| C02 | The supplied rectangular fixed-lattice fixture yields exactly 6 tables, 24 modules, 13.2 kWp, 168 m² gross area, 120 m² buildable area and 48 m² physical/projected module area. Every expected origin matches. |
| C03 | The supplied obstacle fixture yields exactly 5 tables, 20 modules and 11 kWp. It rejects the table at (4,1) rather than deleting arbitrary modules. Buildable area is 112 m². |
| C04 | Portrait/landscape, nonzero module gaps and tilt dimensions match independent hand calculations. At least one test distinguishes module area from table-envelope area. |
| C05 | The 3-4-5 pitch fixture returns D=4, H=3, shadow gap=3 and pitch=7 m at 45° solar elevation; flat tilt, clearance-dominated pitch, invalid elevation and near-horizon limits are exercised. |
| C06 | Azimuths 0/90/180/270 and 17/37/73° give independently checked axis directions, corners and relative heights. Reversed azimuth or downward/upward confusion must be caught. |
| C07 | Concave-notch and hole fixtures reject a rectangle whose centre/four corners can pass but whose footprint crosses a forbidden region. Test full footprint validity, not just counts. |
| C08 | MultiPolygon components are all considered; large setback/complete exclusion returns a successful empty layout with truthful null denominator ratios. |
| C09 | Setback and exclusion-distance requirements are checked against original geometry. Arc approximation and tangent/just-inside/just-outside cases cannot produce an unsafe placement. |
| C10 | Tables and modules do not overlap; every module belongs to exactly one table; table and module totals agree with exports. A separately implemented result verifier detects deliberately corrupted outputs. |
| C11 | Translate equivalent input and anchor by (500000,4000000), (7000000,9000000) and a negative supported offset at azimuths 0/17/37/73/90/180/270. Counts and lattice membership are unchanged; translated-back corners agree within 1e-6 m. At least 21 translated/azimuth pairs are run. |
| C12 | Input magnitudes, site extent, dimensions and candidate/output limits are enforced before unbounded work. Out-of-envelope inputs get typed errors; they do not crash or hang. |
| C13 | All nine documented phase candidates are evaluated, including fixed phase zero; selected count is at least zero-phase count; deterministic tie-break, score table and bounded-optimality label are verified. |
| C14 | Equivalent accepted input normalization and repeated runs produce identical numerical payload digests; changing a geometry-affecting input changes identity. Timestamps/interface wrappers do not change numerical identity. |

## Service, persistence and assistant access

| Gate | Acceptance |
|---|---|
| S01 | CLI and HTTP execute the analytic fixture, return the same normalized summary/result identity, and propagate the same domain errors. |
| S02 | A real MCP client initializes the stdio server, lists tools, creates a project, calculates pitch, generates a layout, pages coordinates and exports artifacts. Retain the complete bounded transcript. Direct handler unit tests alone do not count. |
| S03 | MCP/HTTP/CLI use the same application service and result store; a result created through one is read correctly through the others. Transport schemas are documented. |
| S04 | Two separate processes update the same project from one expected revision: exactly one succeeds, the other gets a revision conflict and persisted data is valid. |
| S05 | Restart the service and read existing project/results/pages/exports. Also interrupt one generation/export at a controlled write point; no partial artifact is presented as a successful result. |
| S06 | Page through a large result using bounded pages; every item occurs exactly once in stable order. Invalid cursor/range is typed. A measured summary/page read does not load the full coordinate result. |
| S07 | Export paths remain inside the managed output root; malformed IDs/formats and path traversal cannot read or overwrite unrelated files. No raw shell interpolation is used for tool or renderer execution. |

## Browser and drawings

| Gate | Acceptance |
|---|---|
| V01 | In a real browser: import fixture, alter a parameter, generate, inspect totals, save/reload project and download an export. Capture at least one screenshot of the whole usable application. |
| V02 | Delay generation, edit inputs before completion, then release the response. The old result is labelled historical/outdated, new edits remain dirty, and an old response cannot overwrite a newer result selection. |
| V03 | Inspect plan renders at overview and close-up for the analytic, concave/hole and projected-coordinate fixtures. North arrow, scale, legend, units, boundaries, exclusions and actual module gaps are correct. Text does not cover the geometry or disappear off the page. |
| V04 | SVG vector geometry matches the immutable result. DXF reopens using a parser with metre units, correct entity counts/layers and original coordinate extents. CSV/JSON match every module ID and quantity. |
| V05 | Calculation report reproduces table dimensions, count × power arithmetic and area denominators; it states relative height and limited pitch assumptions and invents no energy/electrical/structural outputs. |

## Reproducibility and delivery

| Gate | Acceptance |
|---|---|
| D01 | Fresh cloud checkout installs from documented locks and reproduces the analytic CLI workflow and test commands. No private local path, account, weather API, LLM or CAD application is required. |
| D02 | A fixture producing at least 10,000 modules generates and verifies in at most 20 s with measured peak process-tree memory at most 512 MiB on the declared runner. Exports are measured separately. If the runner cannot meet this, report the actual numbers and fail the performance gate; do not hide the benchmark. |
| D03 | A 25,000-module stress fixture completes or is rejected by the declared limit before committing partial output. Candidate bounds and a finite timeout/cancellation policy are demonstrated. |
| D04 | Tests, actual browser checks, real MCP smoke and benchmark run against the final code; acceptance evidence binds to its commit. Fixes made after that run trigger appropriate reruns. |
| D05 | Source archive and Git bundle are attached as downloadable artifacts with SHA-256; extraction/bundle integrity is checked. No cache, credentials or giant reference checkout is accidentally included. |
| D06 | Delivery report separates verified behavior, reference-derived observations, modelling assumptions, untested platforms and remaining failures. New-code release licence and third-party obligations are recorded without making unsupported legal assurances. |

## How to keep verification independent

For the rectangular cases, derive candidate counts from explicit intervals, not a call back into the production generator. For tilted modules, use the 3-4-5 geometry and a second calculation path. For adversarial geometry, construct known crossings and corrupt an output deliberately. Property tests should use controlled seeds and retain failing inputs. Comparing two wrappers around the same function is not independent numerical verification.

Do not require our lattice to match a reference application's undocumented optimization choice. Compare mathematical invariants and explicitly aligned subproblems; investigate differences instead of changing expected values to match the implementation.

## Exact fixture arithmetic

Rectangle: 12×14 m, 1 m setback on each side → 10×12 m admissible rectangle. Portrait modules are 1×2 m. Two columns and two rows, no module gaps → table 2×4 m and 4 modules/table. Along-width period is 3 m and row pitch is 5 m. With anchor (1,1), origins are `(1,1),(4,1),(7,1),(1,6),(4,6),(7,6)`. There are 6 tables and 24 modules; `24×550/1000 = 13.2 kWp`.

Obstacle: exclude the rectangle (4,1)–(6,5), no extra keepout. It removes exactly the table at (4,1). There are 20 modules and 11 kWp. The 8 m² obstacle reduces buildable area from 120 to 112 m². Exact boundary tangency is allowed; overlap with its interior is not.

Tilted pitch: synthetic module slope length 5 m and width 2 m; one per table; tilt `36.86989764584402°`. Projected depth is 4 m, rise is 3 m; 45° solar elevation gives 3 m shadow clear gap and 7 m pitch. At lower-edge relative height 0.8 m, uphill corners reach 3.8 m. All expectations are exact analytic values with 1e-9 tolerance for trigonometric evaluation.
