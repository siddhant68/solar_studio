# Delivery report: Solar Studio Module 01 (site to layout)

Source commit under test: `SOURCE_COMMIT` (branch `claude/kind-cerf-gu33em`). The gate table in `reports/ACCEPTANCE.json` is bound to that commit by git tree IDs for `src/`, `tests/`, `scripts/`, the locks, the fixtures and the probes. Later delivery commits change only reports and evidence.

**Summary.** GATE_SUMMARY. The module computes, verifies, stores and exports flat-site table layouts through a browser, CLI, HTTP and MCP. It reproduces every analytic fixture exactly.

The one material shortfall is in the reference investigation. REA's static JavaScript analysis could not finish the reference's 917 kB main bundle within 300 s, 1,500 s or 2,400 s. That chunk's control path was instead located with REA's runtime execution coverage, and R02 is marked pass on that basis with the limitation stated. Judge it below.

## Verified behaviour

Every item below was run against the source commit; commands and evidence paths are in `reports/ACCEPTANCE.json`.

- **Analytic fixtures (C02, C03, C07, C08).**
  - Rectangle: 6 tables, 24 modules, 13.2 kWp, 168 / 120 / 48 m², all six origins.
  - Obstacle: 5 tables, 20 modules, 11 kWp, buildable 112 m². Exactly the (4,1) table is rejected, for `exclusion:EX-1`.
  - MultiPolygon: 12 tables, 48 modules, 26.4 kWp, gross 336 m², buildable 240 m².
  - Concave notch and hole: 0 tables, although the corners and centre of the trap candidate lie inside the site.
  - Fully excluded sites: an empty, successful layout with null buildable ratios.
  - Expected origins come from independent interval arithmetic (`tests/independent.py`), not from the generator.
- **Geometry conventions (C04, C06).**
  - Portrait, landscape, gaps and tilt match hand calculations (W 6.2, L 2.05, D 1.64, H 1.23 for the landscape case).
  - The 3-4-5 table rises 3 m over 4 m horizontal, with corner heights 0.8 m and 3.8 m.
  - Azimuths 0/90/180/270 give exact axes; for 17/37/73 the bearing of −v equals A, and the upper edge is always behind the facing side.
- **Pitch calculator (C05).** For the 3-4-5 fixture: D = 4, H = 3, shadow gap 3, pitch 7. Also checked: flat tilt, clearance-dominated pitch, invalid elevation, near-horizon refusal (minimum 1°), and azimuth/date inputs refused.
- **Tolerance policy (C09).**
  - Exact tangency to setbacks and keepouts is kept; a 2⁻⁴⁰ m violation is rejected (exact rational re-check).
  - Keepout and reflex-vertex setback arcs are true circles. The tests build tables a chord-polygon method would wrongly accept, and the engine rejects them.
- **Verifier (C10).** The independent verifier passes all fixture results. It detects a table moved into an exclusion, a moved module, a wrong height, dropped or orphan modules, duplicated or overlapping tables, a tampered capacity or ratio, and a table placed across a hole.
- **Translation and rotation (C11).** All 21 translated/azimuth pairs keep identical lattice membership, with translated-back corners within 9×10⁻¹⁰ m. A rotated, projected regression (azimuth 197, keepout) is stable.
- **Limits (C12, D03).** Coordinates, extent, module dimensions, anchor distance, candidates, output modules and a finite timeout all produce typed `RESOURCE_LIMIT` before unbounded work, and nothing is stored.
- **Phase search and identity (C13, C14).** Nine phases are scored with a stable tie-break and the `best_of_evaluated_candidates` label; one test site rewards a phase shift. Equivalent inputs (int vs float, 540° vs 180°, a renamed project) share input digest, result ID and payload digest; geometry changes alter all three.
- **Interfaces (S01–S07).**
  - CLI and HTTP return the same result identity and the same domain errors.
  - A real MCP SDK client session covers initialize, list, pitch, create, CAS update, conflict, generate, paging, exports and typed errors, with the full JSON-RPC wire transcript retained. A second, independent client (MCP Inspector CLI 2.12.0, TypeScript) got the same result ID for the rectangle.
  - Two OS processes racing one expected revision: exactly one wins, repeated 3 times.
  - SIGKILL at two write points leaves no result rows. A killed export leaves only an unreferenced `.partial`.
  - Cursor paging over 10,000+ modules visits each item once, in order. Summary and page reads peak far below the stored coordinate volume.
  - Export paths cannot escape the managed root, including through a symlinked folder; no shell is used.
- **Browser (V01–V03).** Driven in real Chromium:
  - Import a fixture, edit tilt, generate, read totals, reload the project by URL, download the bundle.
  - Delayed response: the old result is labelled historical and the edits stay dirty. A late response from an older generation does not replace the newer result, and the server keeps the newer selection.
  - Overview and close-up plans for the rectangle, concave notch, hole and projected/rotated examples: north arrow, scale (zoom-aware), legend, units, boundaries, exclusions, keepout arcs and the 0.02 m module gaps. Side-panel text never overlaps the plan and stays on the page. I also inspected the PNGs visually.
- **Exports (V04, V05).**
  - SVG vertices map back to every module and table within 1e-9 m. Page millimetres and plan metres stay coherent: plan width = viewBox m × 1000 / scale.
  - The DXF reopens with ezdxf: metres, 8 named layers, exact entity counts, exact site extents, IDs in XDATA.
  - CSV and JSON round-trip every module exactly. The bundle manifest hashes match.
  - Exports are byte-deterministic.
  - The report reproduces the count × power arithmetic and denominators and states its assumptions, with no kWh, AC, electrical or structural numbers.
- **Performance (D02).** BENCH_D02.
- **Reproduction and packaging (D01, D05).** REPRO_SUMMARY

## Reference-derived observations

These are observations of other software. See `reports/REFERENCE_FINDINGS.md` for authorities and identities.

- REA built-artifact analysis:
  - Static: completed for `index.html`, the worker and two chunks (Evidence `ev_4aace5846a3b…`).
  - Static: the main chunk timed out three times.
  - Runtime: `capture_browser_scenario` for small array, pitch/tilt change, and save/reload.
  - Runtime: `observe_web_execution` located the pitch control handler `l({pitchM:z(Math.max(.5,…))})`, the derived-metric recomputation, and an autosave `setItem`.
  - All of these are byte ranges in the built bundle.
- The reference silently clamps and raises pitch, infers AC capacity as DC/1.2, persists derived numbers inside the design, and displays rounded values. Module 01 rejects infeasible pitch, infers no electrical values, keeps immutable results separate from revisioned inputs, and shows exact inputs.
- The reference's minimum-pitch formula agrees with ours on the aligned subproblem (7 m for the 3-4-5 case). PVPlant's table formula matches ours but works in millimetres, and its placement uses an axis-aligned grid with a 10 mm point tolerance.
- **WASM internals were not examined.** WABT was unavailable for REA's `inspect_wasm_artifact`. Static calls from the main chunk into WASM are unresolved.

## Modelling assumptions

- Flat ground and one metric Cartesian frame (x East, y North, frame north). There is no CRS transformation or grid convergence.
- Heights are synthetic and relative (`relative_flat_datum`).
- Tables are uniform rectangles with one azimuth and tilt. Module gaps are measured in the table plane.
- Row pitch is user-supplied, lower edge to lower edge, and is checked only for physical overlap and the minimum clear gap.
- The pitch calculator is a 2D estimate at one solar elevation, assuming the sun is perpendicular to the rows.
- The phase search is bounded to 3×3 offsets; the result is the best of the evaluated candidates, not an optimum.
- DC capacity is module count × supplied nameplate power. Nothing else electrical is computed.
- Buildable area polygonizes arcs, and is reported with bounds.

## Untested platforms

- macOS and Windows: not run. Expected to work for the engine and service; the fault-injection tests and the bash helpers are POSIX-only.
- Other browsers: only Chromium 153 was tested; Firefox and WebKit were not.
- Python 3.13+: not run (3.12.3 was tested).

## Remaining failures and limitations

FAILURE_LIST

- **R02 limitation (not a recorded failure).** REA static analysis of `assets/index-8KvU91kB.js` did not complete in three attempts. A future run could try a larger budget, a machine with more single-core speed, or a newer REA release. Runtime coverage evidence is the substitute used here.
- `git push` from the build session was refused because the Claude GitHub App has no access to `siddhant68/solar_studio`. The deliverable is the attached Git bundle.
- New-code licence: `pyproject.toml` declares **Apache-2.0** as a proposal. Confirm or change it before publishing.

## Significant bugs found and fixed

See `docs/IMPLEMENTATION_NOTES.md`. Briefly:
- Non-deterministic DXF bytes (ezdxf timestamps and GUIDs) broke the export hashes; now fixed and tested.
- An HTTP download of a recorded export whose file had been altered now rebuilds it instead of failing.
- The REA coverage probe acted before the window armed; it now synchronises on REA's armed signal.
- A wrong keepout test geometry and two UI layout defects were corrected.

## Licences

- New code: Apache-2.0, as proposed above.
- Dependencies (from `uv.lock`): Shapely/GEOS (BSD-3 / LGPL-2.1 bundled library), numpy (BSD-3 and bundled terms), ezdxf (MIT), MCP SDK (MIT), Starlette/uvicorn (BSD-3), jsonschema (MIT), pydantic (MIT), certifi (MPL-2.0) and others; see `docs/IMPLEMENTATION_NOTES.md`.
- No code or data from the agrivoltaic planner (Apache-2.0 / CC BY 4.0), PVPlant (LGPL-2-or-later headers with no licence file) or pvlib (BSD-3) is included.
- This is a factual inventory, not legal advice.

## Next actions for Module 02 (terrain)

1. Accept a surveyed terrain input (TIN or DEM with its CRS and vertical datum) and keep `relative_flat_datum` results separate from terrain-fitted results by `z_kind`.
2. Fit a rack plane per table from the immutable table records, keyed by the existing `table_id` / `(i, j)`. Report slope limits and per-pile heights as new, explicitly verified quantities.
3. Add terrain-aware exclusions (slope above a limit) as additional forbidden regions, decided against the original geometry like keepouts.
4. Extend the verifier with independent terrain checks before any terrain result is persisted.
5. Re-run REA on the reference's main chunk with a larger budget only if a terrain-related reference question needs it.
