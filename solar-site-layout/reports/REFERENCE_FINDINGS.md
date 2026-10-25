# Reference findings (Module 01)

Investigation date: 25 October 2026, Linux x86_64 cloud container. Every row names its **evidence authority**, and the authorities are kept separate:

- **REA-static**: REA `analyze_javascript_application` Evidence on the built artifact.
- **REA-runtime**: REA `capture_browser_scenario` or `observe_web_execution` Evidence.
- **PW-runtime**: ordinary Playwright observation, not REA.
- **Source**: ordinary reading of authored source; not REA, and not proof of what the build does.
- **Independent calc**: our own arithmetic, done here.

REA graphs and runtime traces establish structure and behaviour only. Numerical correctness of *our* engine comes from the independent fixtures and tests, never from agreement with a reference.

## Artifact and tool identity (R01)

| Item | Value |
|---|---|
| Reference | agrivoltaic-garden-planner @ `43118b3939a91df5ba641a3b0470022ff7ecc5c7` (pinned commit, no substitution) |
| Build | `rustup target add wasm32-unknown-unknown`, `bun install --frozen-lockfile`, `VITE_AGENT=off bun run build`. Agent panel off. Deploy, model-download, secret and wrangler scripts were **not** run. |
| Toolchain | bun 1.4.4 (the package declares bun@1.4.2), rustc/cargo 1.97.0, node 22.22.0 for package scripts |
| Built artifact | `dist/`: 35 files (6 HTML, 6 JS, 1 WASM, 1 CSS, 11 data, 4 fonts, 4 images, 1 text, 1 `_headers`), **no source maps**. REA-reported directory digest `4e9098e6…3c413f`. Per-file SHA-256 in `references/manifest.json`. |
| Serving | The exact analysed `dist/` was served by `python -m http.server` on 127.0.0.1:4173. Chromium sent all non-loopback traffic to a closed proxy (`references/probes/chromium-offline.sh`), or Playwright aborted it. No external response was observed or mocked: the weather fallbacks (power.larc.nasa.gov) were aborted and the app used its bundled example garden. |
| REA | `rea-agents@6.8.0`, integrity `sha512-9QDeRnGq…ZA9ww==` (matches the handoff screening), MIT. It ran on node v24.22.1 (an isolated tarball with verified SHA256SUMS) because the container's node 22.22.0 is outside REA's `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1`. `rea doctor` reports the native providers (Hopper, Ghidra, IDA, JADX) as missing; none are needed for JavaScript. `rea setup` was not run and no MCP client registration was changed. |
| Licences | Code Apache-2.0; `docs/`, `data/` and `public/data/` CC BY 4.0; third-party data terms in `public/data/manifest.json` (NOTICE). **No reference code or data is copied into this project.** |
| PVPlant | @ `7852ee562c92706e5e3e5d095cefccd5070b18d3`. `PVPlantRack.py` and `PVPlantPlacement.py` headers say LGPL v2 or later and refer to a "LICENCE text file", but no licence file exists at this commit. Concepts only; nothing copied. |
| pvlib | BSD-3-Clause. Not installed: the pitch calculator takes a supplied solar elevation and needs no ephemeris. Kept for the energy module. |

## REA analysis record (R02)

| Attempt | Scope | Outcome | Retained |
|---|---|---|---|
| 1 | whole `dist/` (16 relevant files) | `provider_timeout` after the 300 s per-source deadline, in `CITATIONS.csl` / `SceneCanvas` (1.2 MB three.js chunk) | `evidence/rea/static/attempt1-full-dist.*` |
| 2 | `index.html` + `index`, `rows`, `recommend`, worker chunks; 1,500 s per source | the other files completed; **`assets/index-8KvU91kB.js` (917 kB) timed out** in REA's static phase | `attempt2-selected-5-files.*` (partial graph in the separate evidence archive) |
| 3 | `index.html` + `index-8KvU91kB.js` only; semantic limits lowered (20k nodes, 5k unknowns); 2,400 s | **`provider_timeout` after 2,400 s**, again in the static phase. Lowering the semantic limits did not help. | `attempt3-index-reduced-limits.*` |
| 4 | `index.html` + `entry.worker-BWZeDHYo.js` + `rows-06xZe35N.js` + `recommend-CNrji3tC.js` | **completed, exit 0, 34.5 s**; Evidence `ev_4aace5846a3b…`; 232 graph nodes (201 module nodes: 198 exports, 3 source modules), 624 edges, 26,734 semantic nodes, 402 findings, 3 JS files parsed, 0 parse failures | `attempt4-html-worker-chunks.summary.json`, `…evidence-bundle.json.gz` (parseable; checked by the acceptance builder) |
| exec | REA `observe_web_execution` (CDP precise coverage) on the live built page, idle window and row-pitch/tilt change window | idle window: 0 functions executed. Action window: 678 functions in `index-8KvU91kB.js`, 1,200 in `SceneCanvas` | `evidence/rea/execution/` |

The main chunk never finished REA *static* analysis inside the budgets tried. **REA runtime coverage was therefore used to locate the UI/state path inside it** (below), and that limit is stated wherever the result is used.

## Claim table

| # | Question | Input | Observed result | Authority | Exact identity | Coverage limit | Implication |
|---|---|---|---|---|---|---|---|
| F1 | Which built assets exist? | built `dist/` | 6 HTML, 6 JS chunks, 1 WASM (`agv-sim.wasm`), data grids, fonts; no source maps | Build + SHA-256 | `references/manifest.json` | Hashes only | Source maps cannot map bundle offsets to source; the mapping below comes from the excerpts REA retained |
| F2 | Where is the row-pitch control's handler and state update? | change `control-array-pitch` 9 → 6 m, then tilt 25° → 35°, inside REA's armed window | Executed function `nI` @ `index-8KvU91kB.js` UTF-16 offsets 756961–762162 (array panel; holds `control-array-pitch`). Its pitch `onChange` @ 758183–758221 ran once: `e=>l({pitchM:z(Math.max(.5,qA(e,t)))})`. Tilt `onChange` @ 756285–756325: `r=>t({...e,tracker:{...n,tiltDeg:R(r)}})` | REA-runtime (`observe_web_execution`) | `evidence/rea/execution/observe-pitch-change.json.gz`, `coverage-matches.json`; script SHA-256 `9a048fab…f226` | One interaction; counts are per window; dynamic dispatch not resolved | The pitch input is **clamped silently** to ≥ 0.5 m and unit-converted in the handler (D2) |
| F3 | What derived values recompute on that change? | same window | `ud` @ 344659–344882 computes `groundCoverRatio: ed(collectorWidthM, pitchM)`, `projectedGroundCoverRatio`, `maxHeightM`, `nameplateDcKw`, and `nameplateAcKw: $u(ld(e))`; `md` @ 345803–346639 builds panel corners (TS `panelSnapshot`); `kp` @ 406628–407641 and `Ep` @ 405976–406197 | REA-runtime | as F2 | Static callers of these functions are not resolved (attempt 3 did not complete) | AC capacity is **inferred from DC** in the reference; Module 01 must not do that (D4) |
| F4 | Does the reference ever change pitch for the user? | `Ep` excerpt from the same Evidence | For non-fixed trackers: `pitchM: z(Math.max(r, n))` raises the pitch to the collector width, and clearance likewise | REA-runtime (retained excerpt) | `coverage-matches.json` entry `Ep` | Fixed tilt returns unchanged; the tracker branch was not exercised | We reject an infeasible pitch with `INVALID_PITCH` instead of changing it (D2) |
| F5 | Is state written on change? | same window | `O_` @ 438296–438485 executed; it contains `localStorage.setItem` | REA-runtime | `coverage-storage.json` | No call-stack attribution | The design autosaves; there are no immutable results or revisions (D5) |
| F6 | Small array: what do the readouts say? | example garden, rows 3 → 2, panels per row 14 → 4 | Nameplate 36.1 kW → 6.9 kW. GCR 39.2 %, projected 35.5 %, max height 4.09 m, all unchanged | REA-runtime S1 + PW-runtime | `evidence/rea/runtime-scenarios/R03-S1-*`; `evidence/runtime/agv/playwright-scenarios.json` | One example | Independent calc: 2 rows × 4 × round(3.524/1.762) = 2 → 16 modules × 430 W = **6.88 kW**, matching |
| F7 | Pitch and tilt change | pitch 9 → 6, tilt 25 → 35 | GCR 39.2 % → 58.7 %; projected 35.5 % → 53.2 % → 48.1 %; max height 4.09 → 4.62 m | REA-runtime S2 + PW-runtime | `R03-S2-*` | Example garden only | Independent calc: 3.524/6 = 0.5873; 3.524·cos35°/6 = 0.4811; 2.6 + 3.524·sin35° = 4.621 m, all matching. **Pitch there is centre-to-centre**, which equals our lower-edge-to-lower-edge for identical rows (D1) |
| F8 | Save and reload: what persists? | tilt 33, pitch 7.5, Save, reload | Controls restored (33°, 7.5 m); readouts GCR 47.0 %, projected 39.4 %, height 4.52 m. Stored design has 20 top-level keys including `plot.arrays[].geometry/tracker/module/derived`; `derived` includes `nameplateAcKw = DC/1.2`. Energy status returns `idle` (recomputed on demand). REA records only SHA-256 digests of storage values | REA-runtime S3 + PW-runtime | `R03-S3-*`; `playwright-scenarios.json` | Example garden; one browser | Inputs and some derived numbers are persisted together; there is no revision or result identity (D5) |
| F9 | Do displayed values equal stored values? | live inputs vs stored JSON | The collector width field shows `3.5`, but `3.524` is stored; the UI rounds to a tenth | PW-runtime | `playwright-scenarios.json` | One field checked | Our UI shows the exact values sent to the engine (D6) |
| F10 | Is the DOM snapshot a reliable value source? | REA DOM capture after `fill` | Number-input `value` attributes can lag the live value (modules-per-row stayed `14` while the readout showed 6.9 kW) | REA-runtime DOM vs readout | `R03-S1-*/summary.json` | React attribute syncing | Evidence must use live properties or readouts, not DOM attributes (method note) |
| F11 | JS → WASM boundary (R05) | static worker chunk; live page | Static: string literal `"/agv-sim.wasm"` in `assets/entry.worker-BWZeDHYo.js` line 161, column 9366 (semantic node `jsrg_node_fc5557e8…`, inside top-level function `jsrg_node_22e539e0…`). Runtime: a `wasm://wasm/agv_sim.wasm-0006c6f2` script exists in the page's main execution context (REA excluded WASM bytecode from JS coverage) | REA-static + REA-runtime | `attempt4-…evidence-bundle.json.gz`; `execution/first-attempt-observe-pitch-change.json` | **WASM internals not examined**: WABT is not installed, so REA `inspect_wasm_artifact` could not run. Main-chunk static calls into WASM are unresolved (attempt 3) | Unknown which numerics run in WASM in each path. The UI recomputation in F3 executed the **JS** `panelSnapshot` (`md`) |
| F12 | What does the authored Rust export? | `crates/agv-sim/src/wasm.rs` | `agv_alloc_f64`, `agv_free_f64`, `agv_spa_series`, `agv_decompose_series`, `agv_annual_chain`, `agv_panel_snapshot`, `agv_beam_visibility`; f64-buffer ABI with no wasm-bindgen; `src/sim/rust-core.ts` packs `pitchM` at `flat[1]` | Source | repo @ pin | Source only, not the binary | Panel geometry exists in both TS and Rust in the reference (a parity test exists). Our engine has one implementation plus an independent verifier |
| F13 | Reference panel geometry conventions | `src/sim/geometry.ts` `panelSnapshot` | Row azimuth (direction rows run) and surface azimuth are **separate inputs**; a module's along-row length is `rowLengthM / modulesPerRow` (module width and gaps are ignored); stack count `= round(collectorWidth / module.heightM)`; corners listed lower-left, lower-right, upper-right, upper-left, with the lower edge on the facing side | Source (the REA-runtime excerpt of `md` agrees) | `geometry.ts` @ pin | Source | We use **one** facing azimuth and derive the row direction (no contradictory pairs), keep real module sizes and gaps, and use the same corner order with the lower edge on the facing side (D3) |
| F14 | Minimum pitch formula | `minimumPitchM` (source) | `collectorWidth·(cos β + sin β / tan θ)`, with θ the sun **profile** angle | Source | `geometry.ts` @ pin | Source; formula not executed in our runs | Matches ours: `D + H/tan α` with α the elevation when the sun is perpendicular to the rows (profile = elevation). 5·(0.8 + 0.6/1) = 7 m for the 3-4-5 fixture (D1) |
| F15 | PVPlant table parameterization (R06) | `PVPlantRack.py` | `totalw = w·cols + colgap·(cols−1)`, `totalh = h·rows + rowgap·(rows−1)`; portrait w = ModuleWidth, h = ModuleHeight; landscape swaps them. Units are **FreeCAD millimetres** (ModuleWidth 1130, ModuleHeight 2250, gaps 20) | Source | `PVPlantRack.py` sha256 in manifest | No FreeCAD run | Same W/L formula as ours; we use **metres** and convert nothing |
| F16 | PVPlant placement | `PVPlantPlacement.py` | Axis-aligned `np.arange` grid from bounding boxes; row step = `editGapRows + max(rack bbox X, Y)`; accepted when `Area.isInside(point, 10 mm tolerance)` and a `cut` leaves no vertices | Source | `PVPlantPlacement.py` sha256 in manifest | Not executed | **Difference:** PVPlant's pitch is clear gap + largest bbox side (not tilt-projected depth), its grid is world-axis aligned, and containment uses a 10 mm point tolerance. Ours uses an azimuth-aligned lattice, exact full-footprint predicates and no positive tolerance (D7) |

## Decision table (R04, R07)

| # | Decision | Reuse / adapt / implement | Evidence that drove or confirmed it |
|---|---|---|---|
| D1 | Row pitch is lower edge to lower edge; the 2D calculator is `max(D + gap, D + H/tan α)` with α = elevation and the sun perpendicular to the rows | Implemented from the documented formula | F7 (centre-to-centre equals lower-edge for identical rows), F14 (reference formula agrees on the aligned subproblem) |
| D2 | An infeasible pitch is **rejected** (`INVALID_PITCH`) and never clamped or raised | Implemented | F2 and F4: the reference silently clamps to 0.5 m and raises pitch for trackers; the brief forbids quiet changes |
| D3 | One facing azimuth determines u and v; corner order c0..c3 with the lower edge on the facing side; real module size and gaps | Implemented | F13 (separate row/surface azimuths allow contradictory input; modules are stretched to row length), F7 |
| D4 | Only the supplied nameplate power is used: no AC, inverter or electrical inference | Implemented | F3 and F8 (reference stores `nameplateAcKw = DC/1.2`) |
| D5 | Editable projects with integer revisions and CAS; immutable, content-addressed results; derived numbers never stored inside the editable spec | Implemented (SQLite) | F5 and F8 (autosave of mixed inputs and derived values, no revision identity) |
| D6 | The UI shows exact entered values with units and labels results current/outdated by revision | Implemented | F9 (rounded display hides the stored value) |
| D7 | Containment and setbacks use exact full-footprint predicates against the original geometry, with no positive tolerance | Implemented with Shapely/GEOS + exact rationals | F16 (point/bbox tolerance approach), handoff C07/C09 |
| D8 | Geometry, file formats, MCP, HTTP: reuse maintained libraries | **Reuse**: Shapely 2.2.0 / GEOS 3.14.1 (BSD-3 / LGPL-2.1), ezdxf 1.4.5 (MIT), MCP Python SDK 2.3.0 (MIT), Starlette/uvicorn (BSD-3), jsonschema (MIT), numpy (BSD-3) | Brief: do not reimplement Boolean operations, DXF or MCP transport |
| D9 | No code copied or adapted from the agrivoltaic planner, PVPlant or pvlib | No reuse | Licences recorded (F1, F15); concepts only |

## Rejected assumptions

- "REA analysis of the whole bundle is quick": the main chunk did not finish in the budgets tried. We did not claim static coverage of it.
- "The DOM snapshot shows the current input value": false for focused number inputs (F10).
- "The reference's GCR is our ground coverage": the reference GCR is collector width / pitch. Ours is projected **module** area / site area, with gaps excluded.
- "Agreement with the reference validates our engine": not used. Only aligned subproblems (F6, F7, F14) are compared, and our correctness rests on independent fixtures.
