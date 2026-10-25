# Reference investigation and REA plan

Research date: 25 October 2026. These are screened candidates, not applications we have already run or validated. Source/API inspection was performed while preparing the brief; no REA execution is claimed by this package.

## Selected references

### A. Primary artifact target: Agrivoltaic garden planner

- Repository: https://github.com/peterklingelhofer/agrivoltaic-garden-planner
- Investigate commit `43118b3939a91df5ba641a3b0470022ff7ecc5c7`, or explicitly record why unavailable and pin the replacement.
- Code: Apache-2.0. Documentation/data: separate CC BY 4.0 terms; third-party inputs have their own notices. Inspect `LICENSE`, `LICENSE-DOCS`, `NOTICE` and data notices before reuse.
- It contains a browser application and a Rust/WASM simulation component. Its declared focus is small garden arrays and light available below them. It is not a validated utility-scale polygon packing engine.
- Useful questions: how array dimensions and row spacing become geometry; how parameter changes reach rendered modules; how saved state is restored; which calculations live in JavaScript versus WASM.
- Relevant source areas: `src/scene/`, `src/sim/`, `src/state/`, `src/recommend/`, `crates/agv-sim/`. Use ordinary repository tools for these source questions.

REA artifact target: the actual local production browser build, primarily its emitted HTML/JavaScript assets. Analyze the built artifact, not the complete authored source tree just to tick a REA box. Record the exact build recipe and digests. An upstream shipped build may be used instead only if its origin and version are established; do not silently attribute the live site to a source commit.

The pinned package declares Bun and Node, and its full build includes Rust/WASM. Inspect the scripts first. Use its normal local build when feasible. Keep the agent panel off. Avoid unrelated deployment/model acquisition paths. For browser scenarios use deterministic local data fixtures or its bundled example, documenting any mocked external data. Do not count mocked data as an observed external service response.

### B. Secondary CAD/design reference: PVPlant with FreeCAD

- Repository: https://github.com/JavierBrana/PVPlant
- Pin `7852ee562c92706e5e3e5d095cefccd5070b18d3`.
- The repository describes a PV plant designer using FreeCAD. `PVPlantRack.py` and `PVPlantPlacement.py` contain module/table and placement-related code.
- The inspected file headers specify LGPL version 2 or later. GitHub's repository-level licence field was empty, so do not declare a blanket licence for every file or bundled dependency. Record the exact files/headers used and any missing licence text.
- Use it to understand domain concepts and units. Reading Python source is ordinary source analysis, not a REA run.
- FreeCAD is an open-source cross-platform CAD application: https://github.com/FreeCAD/FreeCAD. Treat it as an optional external comparison/adapter, not a required production runtime.

Native FreeCAD decompilation is unnecessary for this assignment. If a specific claim truly needs a compiled artifact, document the question first, acquire a versioned official artifact for the current OS, and use a supported REA provider only if available. A lack of native analysis tools must not block the core layout engine.

### C. Numerical reference: pvlib

- Repository: https://github.com/pvlib/pvlib-python
- Licence: BSD-3-Clause; confirm the installed package version and component terms.
- Documentation: https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.solarposition.get_solarposition.html
- Use for solar convention checks and later modelling. The required pitch calculator consumes a supplied elevation and needs no ephemeris. If adding an optional solar-position probe, make it a separate reference script with timezone-aware times; use the Python implementation rather than separately licensed external SPA C code.

### D. Geometry semantics

- Whole-footprint containment: https://shapely.readthedocs.io/en/stable/reference/shapely.covers.html
- Offset/buffer behavior: https://shapely.readthedocs.io/en/stable/reference/shapely.buffer.html

These establish library behavior, not the correctness of our application. Independent fixtures must detect a faulty use of the library, corner-only checks and invalid numerical tolerances.

## Screened alternatives and why they are not primary targets

| Candidate | Finding | Decision |
|---|---|---|
| SunFarm, https://github.com/funkybooboo/sunfarm | GPL-3.0; at `565d7d92dccbe480d6a3ec069ea4c0ab7d01572c`, `src/main.rs` loads configuration and explicitly reports the core simulation is not implemented. | Reject as an implemented layout oracle. Marketing features do not establish working code. |
| GESPlan, https://github.com/ardanoyan/gesplan | Public browser prototype with layout code; no repository licence detected in API/tree inspection. | Do not treat public availability as a reuse licence. Not needed for this build. |
| Solar Planner / PV-Mapp, https://pv-mapp.com/ | Free/pro product; the apparent GitHub repository returned 404 during screening. | Not established as an open-source target. No paid access or account needed. |
| PV Layout Designer, https://github.com/ganeshgowri-ASA/pv-layout-designer | README states proprietary/all rights reserved despite public code visibility. | Exclude from open-source reuse. |
| solarPlanner-v2, https://github.com/santilinares/solarPlanner-v2 | MIT; broader estimation/project application. | Optional later workflow reference, not a demonstrated polygon/table oracle. |
| SAM, https://sam.nrel.gov/sam-open-source.html | Open-source system performance/financial modelling tools. | Good candidate for the future energy module, outside the first layout goal. |
| QElectroTech, https://qelectrotech.org/ | Electrical drawing application. | Investigate for the future electrical/diagram module, not first-site geometry. |

Our selection is a reasoned fit for inspectability and specific questions. It is not a claim that a single existing project satisfies our complete specification.

## REA environment

Project: https://github.com/morluto/rea

Screened package: `rea-agents@6.8.0`, released 25 October 2026. Release: https://github.com/morluto/rea/releases/tag/rea-agents-6.8.0

The npm metadata inspected during preparation declares Node `^22.23.4 || ^24.22.1 || >=26.12.1`. Verify this against the exact acquired package. Do not assume any Node 22/24 is compatible. Use a compatible container/project runtime; do not change a user's desktop setup.

For a supported existing runtime, the expected CLI route is:

```sh
npx -y rea-agents@6.8.0 --help
npx -y rea-agents@6.8.0 analyze-javascript-application /absolute/path/to/reference/dist --json > /absolute/path/to/evidence/reference-js.json
```

Read the installed help before using flags. Keep complete output on disk; inspect its summary and selected modules rather than flooding chat context. Save exit status, stderr, package version, runtime and input file digests. Do not execute the JSON output or any strings extracted from it.

A connected REA MCP server is optional. If present, use its actual advertised schemas and `analyze_javascript_application` with summary delivery. Reuse retained Evidence references for pages and focused traces. If absent, use the CLI; installing a skill does not create an MCP connection. Do not spend this project repairing desktop MCP registration.

Static JavaScript analysis requires neither Hopper nor Ghidra. The WASM engine is a separate coverage boundary. A JavaScript trace into a WASM call does not establish the algorithm inside that WASM. If supported tooling is already available, optionally inspect the explicit `.wasm` artifact. Otherwise record that limitation and examine authored Rust using ordinary source tools.

For runtime captures, use REA's advertised browser scenario tools if available, with declared actions against the local reference instance. Otherwise use Playwright and label the resulting screenshots/events as ordinary browser runtime evidence. Do not fabricate REA runtime records or rename Playwright output as REA Evidence.

## Questions and experiments

Create `reports/REFERENCE_FINDINGS.md` with one row per claim: question, input, observed result, evidence authority, exact artifact/source identity, coverage limit and implication for our implementation.

| Probe | Question and required record |
|---|---|
| R01 | Inventory the built assets and separate HTML, JS, WASM, data and source maps. Hash them; record source commit/build environment. |
| R02 | Use REA to locate the UI/state path associated with at least one array dimension or row-spacing control. Cite actual returned module IDs/ranges; do not invent names. |
| R03 | Run a small supported array, vary one parameter, and retain before/after geometry or state plus screenshots. Explain units and coordinate conventions. |
| R04 | Change tilt/spacing and save/reload. Determine which inputs and derived outputs are persisted; record only behavior actually exercised. |
| R05 | Identify JavaScript-to-WASM boundaries relevant to these controls. Mark unexamined numerical internals unknown. |
| R06 | Read the relevant PVPlant table/module source. Map concepts to our contract and record at least one difference in scope, units or behavior. |
| R07 | Maintain a decision table: reuse a dependency, adapt licensed code with notices, or implement from a documented formula. Give reasons. |

No fixed panel-count parity is required between different layout algorithms. Compare only matched dimensions, pitch definitions or state behavior after aligning conventions. A mismatch should yield a small reproducible example and a reasoned explanation, not an arbitrary adjustment to our numerical answer.

## Required research artifacts

`references/manifest.json`: repository URLs, commits, artifact hashes, package versions, licences and build recipes.

`evidence/rea/`: complete actual REA Evidence, selected views, commands/stderr and coverage notes.

`evidence/runtime/`: deterministic scenarios, inputs, before/after observations and screenshots.

`reports/REFERENCE_FINDINGS.md`: claim table, useful findings, rejected assumptions and impact on the design.

If a dependency or tool cannot run, capture the exact error once, make one targeted repair or change a documented prerequisite, then continue useful work. Never repeat setup indefinitely or report unavailable observations as successful.
