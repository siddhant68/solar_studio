# Delivery report: Solar Studio Module 01 (site to layout), after the review repair

Source commit under test: `fe15c5fda8345cbc17c2b8dc2a81fd5321fda5ef` (branch `claude/kind-cerf-gu33em`). The gate table in `reports/ACCEPTANCE.json` is bound to that commit by git tree IDs for `src/`, `tests/`, `scripts/`, the locks, the fixtures and the probes. The evidence commit (`4594c5f`) and the delivery commit after it change only evidence, reports and documentation.

**This report replaces the first delivery** (36/36 recorded as pass on `f16944e`, delivered as `f55f4be`). An independent review on 26 October 2026 (`../reviews/module-01/2026-10-26/`) reproduced five defects and a browser 404 at `f55f4be`, so the earlier passes for V01, V02, V04, S05 and C10 rested on evidence that did not exercise those cases. All five findings were reproduced again here, turned into failing regressions, fixed, and the whole acceptance run was repeated on the repaired source.

**Summary.** `reports/ACCEPTANCE.json` records **all 36 gates as pass** over 233 test cases (0 failed, 0 skipped; browser tooling was required, not optional). The numerical core (validation, layout engine, exact kernel, result records) is unchanged, and every analytic fixture still reproduces exactly. The one material shortfall is still in the reference investigation: REA's static analysis did not finish the reference's 917 kB main bundle, and R02 passes on runtime coverage with that limitation stated.

## Review response, finding by finding

| Finding | Reproduced here (before) | Fix | Regression and result (after) |
|---|---|---|---|
| **F1 (P1) input snapshot across autosave** | Reviewer's `browser_races.cjs`: a 24-module result labelled **current** while the saved input had a 1 m module width and the editor 2 m (`evidence/repair/before/browser-races.json`). | Generate captures the editor snapshot synchronously when pressed and saves exactly that JSON; saves are queued, each naming the revision the previous one returned; a result is current only if project, revision and snapshot all match. | Browser V02 "F1 create-delay" (project POST held) and "F1 update-delay" (PUT held): the result is **outdated**, its snapshot equals the saved input, the edit stays dirty, the server revision holds the snapshot, and generating again makes the edit current (16 modules). Both fail on the unrepaired client and pass now. |
| **F2 (P1) stale SVG render** | After the held revision-1 SVG was released, the page showed 24 modules with a revision-1 identity and download link under a "Current result for revision 2" banner. | A result is committed to the page only after its last await, and only if it is still the newest generation of the current editing context. Opening a project, importing a file or loading an example starts a new context and clears the view; late responses go to the session history. | Browser V02 "F2 stale SVG": plan, quantities, status, identity, banner and download link all stay on the revision-2 result. "Project switch" and "import while pending" cover the other interleavings the review asked for. All three fail on the unrepaired client and pass now. |
| **F3 (P2) concurrent export collision** | Reviewer's `adversarial_probes.py`: natural parallel CSV exports and the controlled overlap fail with `FileNotFoundError` (temporary name was PID-only). | `mkstemp` staging per build; per-(result, format) publication lock across threads (`threading.Lock`) and processes (`flock`); downloads stream from the file handle whose bytes were hashed; DXF metadata fixed per document instead of through ezdxf's process-wide option. | `tests/test_review_regressions.py::test_f3_*`: 24 parallel service exports for each of the six formats; a controlled overlap of two writers inside the staging write; 12 parallel DXF exports with the global option untouched; a live server with 24 parallel CSV downloads plus 24 mixed bundle/subformat downloads and 12 parallel export POSTs. Every call succeeds, `X-Content-SHA256` equals the downloaded bytes, the bundle manifest equals the standalone files, no `.partial` remains. Adapted probe: 0/24 failures. |
| **F4 (P2) mutable export context** | JSON bytes at the same path changed after a second project reused the result (`project_sources` grew). | Result exports (json, csv, svg, dxf, report, bundle) contain the result only, live under `RID/v2/` and are write-once (a rebuild that would change an issued file is refused). Project associations are a separate, content-addressed `context` export whose earlier files are kept. The bundle uses one row snapshot and re-hashes each part as it copies it. | `test_f4_*`: after a second project, a renamed revision and a service restart reuse the result, all six result exports keep path and bytes; a new context file appears and the old one is unchanged; a repeat export reuses the same inode; the bundle manifest equals the standalone hashes. |
| **F5 (P2) verifier gaps** | A 123,456 W module record and consistently falsified areas/ratios passed the verifier. | New independent checks: `record_fields` (every contract field of every record), `record_totals` (summed module power and table module counts against the summary), `areas` (own shoelace areas; buildable area bracketed by its own construction with 4× finer arcs) and `payload_integrity` (digest recomputed over exactly the records given). Geometric checks unchanged. | `test_f5_*`: power corruption, uniformly wrong power, falsified gross/buildable areas with consistent ratios, a plausible buildable area with self-consistent bounds, corrupted IDs and lattice fields, corrupted table records and a zeroed payload digest are all rejected; every fixture still verifies. Verification of 10,192 modules takes 0.97 s. |
| **Browser 404** | `GET /favicon.ico` (full Chromium requests it; the headless shell used by the first checks does not), logged with its URL by the extended checks. | `/static/favicon.svg` linked from the page and a `/favicon.ico` route. | The checks run full Chromium and fail on any console error, failed request or HTTP status ≥ 400, each logged with its URL; all "no browser errors" checks pass. |

Two further defects were found while repairing and re-running, and are fixed with regressions:
- **DXF bytes depended on `PYTHONHASHSEED`.** ezdxf orders the CLASSES section by iterating a `set`, so the DXF (and bundle) hashes differed between processes; the first delivery's "byte-deterministic" claim held only within one process. Fixed by sorting per document; `test_exports_identical_across_processes_and_hash_seeds` exports one stored result under three seeds.
- **The generation time limit covered only the layout engine.** The first D03 timeout demonstration passed because the compute stage happened to exceed 0.05 s; on this run's first pass (`d935ff2`) it did not, and the stress result was stored. The service now checks the same deadline after record construction and after verification, before persisting (`test_timeout_covers_records_and_verification_not_only_compute`). That intermediate run's outputs, including the failed timeout case, are preserved in commit `fe15c5f`.

## Verified behaviour

Every item below was run against the source commit; commands and evidence paths are in `reports/ACCEPTANCE.json`.

- **Analytic fixtures (C02, C03, C07, C08).**
  - Rectangle: 6 tables, 24 modules, 13.2 kWp, 168 / 120 / 48 m², all six origins.
  - Obstacle: 5 tables, 20 modules, 11 kWp, buildable 112 m². Exactly the (4,1) table is rejected, for `exclusion:EX-1`.
  - MultiPolygon: 12 tables, 48 modules, 26.4 kWp, gross 336 m², buildable 240 m².
  - Concave notch and hole: 0 tables, although the corners and centre of the trap candidate lie inside the site.
  - Fully excluded sites: an empty, successful layout with null buildable ratios.
  - Expected origins come from independent interval arithmetic (`tests/independent.py`), not from the generator.
- **Geometry conventions (C04, C06).** Portrait, landscape, gaps and tilt match hand calculations (W 6.2, L 2.05, D 1.64, H 1.23 for the landscape case). The 3-4-5 table rises 3 m over 4 m horizontal, with corner heights 0.8 m and 3.8 m. Azimuths 0/90/180/270 give exact axes; for 17/37/73 the bearing of −v equals A, and the upper edge is always behind the facing side.
- **Pitch calculator (C05).** For the 3-4-5 fixture: D = 4, H = 3, shadow gap 3, pitch 7. Also checked: flat tilt, clearance-dominated pitch, invalid elevation, near-horizon refusal (minimum 1°), and azimuth/date inputs refused.
- **Tolerance policy (C09).** Exact tangency to setbacks and keepouts is kept; a 2⁻⁴⁰ m violation is rejected (exact rational re-check). Keepout and reflex-vertex setback arcs are true circles; tables a chord-polygon method would wrongly accept are rejected.
- **Verifier (C10).** The independent verifier passes all fixture results. It detects a table moved into an exclusion, a moved module, a wrong height, dropped or orphan modules, duplicated or overlapping tables, a tampered capacity or ratio, a table placed across a hole, and now also corrupted per-record fields, record totals that disagree with the summary, falsified areas and a wrong payload digest.
- **Translation and rotation (C11).** All 21 translated/azimuth pairs keep identical lattice membership, with translated-back corners within 9×10⁻¹⁰ m. A rotated, projected regression (azimuth 197, keepout) is stable.
- **Limits (C12, D03).** Coordinates, extent, module dimensions, anchor distance, candidates, output modules and a finite timeout all produce typed `RESOURCE_LIMIT` before anything is stored; the timeout now spans record construction and verification.
- **Phase search and identity (C13, C14).** Nine phases are scored with a stable tie-break and the `best_of_evaluated_candidates` label. Equivalent inputs share input digest, result ID and payload digest; geometry changes alter all three.
- **Interfaces (S01–S07).**
  - CLI and HTTP return the same result identity and the same domain errors.
  - A real MCP SDK client session covers initialize, list, pitch, create, CAS update, conflict, generate, paging, exports and typed errors, with the full JSON-RPC wire transcript retained. MCP Inspector CLI 2.12.0 (TypeScript SDK) independently listed the same nine tools, got pitch 7 m and the same rectangle result ID with 24 modules, and the same typed `RESULT_NOT_FOUND`.
  - Two OS processes racing one expected revision: exactly one wins, repeated 3 times.
  - SIGKILL at two write points leaves no result rows. A killed export leaves only an unreferenced `.partial`. Parallel and overlapping exports never fail and leave no `.partial`.
  - Cursor paging over 10,000+ modules visits each item once, in order. Summary and page reads peak far below the stored coordinate volume.
  - Export paths cannot escape the managed root, including through a symlinked folder or the lock directory; no shell is used.
- **Browser (V01–V03).** Driven in full Chromium 153 with Playwright 1.63.0 (pinned), 24 checks:
  - Import a fixture, edit tilt, generate, read totals, reload the project by URL, download the bundle; no console errors, failed requests or HTTP errors.
  - V02: delayed response labelled historical with edits kept dirty; a late older response never overwrites the newer result or the server selection; plus the review regressions above (F1 create/update delay, F2 stale SVG, project switch and import while pending).
  - Overview and close-up plans for the rectangle, concave notch, hole and projected/rotated examples, with north arrow, zoom-aware scale, legend, units, boundaries, exclusions, keepout arcs and 0.02 m module gaps; side-panel text never overlaps the plan. The new screenshots were inspected visually.
- **Exports (V04, V05).**
  - SVG vertices map back to every module and table within 1e-9 m; page millimetres and plan metres stay coherent.
  - The DXF reopens with ezdxf: metres, 8 named layers, exact entity counts, exact site extents, IDs in XDATA.
  - CSV and JSON round-trip every module exactly. The bundle manifest hashes match the standalone files.
  - Result exports are write-once, contain no project context, and are byte-identical across processes and hash seeds.
  - The report reproduces the count × power arithmetic and denominators and states its assumptions, with no kWh, AC, electrical or structural numbers.
- **Performance (D02, D03).** Machine: Intel(R) Xeon(R) Processor @ 2.10GHz, 4 vCPU, 16091 MiB. 10,192 modules (364 tables, projected UTM site with a hole and a keepout) generated and independently verified in **1.58 s** (verification 0.97 s), 2.11 s of process wall time; peak process-tree RSS **81.39 MiB**. All six exports in a fresh process: 2.85 s (DXF 1.45 s; the bundle reuses the issued parts), peak 84.83 MiB. The 25,788-module stress case completed in 4.23 s (4.75 s wall) at 107.09 MiB; the 0.05 s timeout, output limit and candidate limit each returned `RESOURCE_LIMIT` with nothing stored.
- **Reproduction and packaging (D01, D05).** The Git bundle and source ZIP of `4594c5f` (the evidence commit; same source tree as the tested commit) passed every integrity check: `git bundle verify`, the cloned HEAD and tree equal the original, ZIP CRCs pass, the ZIP holds exactly the 265 tracked files, and no caches, virtual environments, databases, keys or reference checkouts are present. SHA-256: `solar_studio-4594c5f1e8.bundle` `27ff8af961199872231c0ef6819c21e16ba4c8552c57f281275a3c8cfe76fc34`, `solar_studio-4594c5f1e8-source.zip` `ad6837053311985c3f3e980cd2dcecd61e23db709715ff2df855fa58ceb16413`. A fresh clone from that bundle, with an empty uv cache, ran `uv sync --frozen`, the CLI workflow (rectangle 24 modules, obstacle 20, pitch 7.0 m) and the full suite: 233 tests passed and none was skipped (233 pass marks and no `s` in `evidence/delivery/reproduction-log.txt`), so the browser checks ran there too. Archives of the final delivery commit are built and verified the same way outside the repository, under `dist/`, and their hashes are listed in the pull request.

## Reference-derived observations

These are observations of other software. See `reports/REFERENCE_FINDINGS.md` for authorities and identities. The repair did not change the reference investigation or its evidence.

- REA built-artifact analysis:
  - Static: completed for `index.html`, the worker and two chunks (Evidence `ev_4aace5846a3b…`).
  - Static: the main chunk timed out three times. **Full static analysis of the main bundle is not claimed.**
  - Runtime: `capture_browser_scenario` for small array, pitch/tilt change, and save/reload.
  - Runtime: `observe_web_execution` located the pitch control handler `l({pitchM:z(Math.max(.5,…))})`, the derived-metric recomputation, and an autosave `setItem`, as byte ranges in the built bundle.
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
- Buildable area polygonizes arcs, and is reported with bounds; the verifier brackets it independently.

## Untested platforms

- macOS and Windows: not run. Expected to work for the engine and service; the fault-injection tests and the bash helpers are POSIX-only, and off POSIX the export publication lock is in-process only (no `flock`).
- Other browsers: only Chromium 153 was tested; Firefox and WebKit were not.
- Python 3.13+: not run (3.12.3 was tested).

## Remaining failures and limitations

- **No gate is recorded as fail, blocked or unexecuted** in this run (see the gate table). The items below are limits of the evidence or the design, not passing results presented as more than they are.
- **R02 limitation (not a recorded failure).** REA static analysis of `assets/index-8KvU91kB.js` did not complete in three attempts; runtime coverage evidence is the substitute. A future run could try a larger budget or a newer REA release.
- **Legacy export files are not migrated.** Stores created by the first delivery keep their v1 files and `exports` rows; the new code neither rewrites nor lists them, and publishes v2 files beside them.
- **Old DXF and bundle hashes** in the first delivery's evidence describe bytes from one process; regenerating them can give a different CLASSES order. The examples in `evidence/examples/` were regenerated.
- **Browser concurrency** is verified for the interleavings the review named (held project create/update, held layout POST, held plan SVG, project switch, import). Other timings follow the same rules but are not individually tested.
- **The timeout bounds what is stored, not every stage's duration.** Within record construction or verification the deadline is checked at stage boundaries, so a stage can overrun the limit by its own duration (about 3 s at 25,788 modules) before `RESOURCE_LIMIT` is returned; resource limits bound the work itself.
- **Licence undecided.** Apache-2.0 is proposed for the new code; the owner has not confirmed it, so no licence file is included and `pyproject.toml` declares none.
- **Pushing works.** The first delivery's note that `git push` was refused is obsolete: `f55f4be` was pushed once the GitHub App had access, and the repair commits are pushed to the same branch.

## Significant bugs found and fixed

See `docs/IMPLEMENTATION_NOTES.md`. In the first build: non-deterministic DXF timestamps and GUIDs; a rebuild path for an altered recorded export; the REA probe arming race; a wrong keepout test geometry and two UI layout defects. In the review repair: F1–F5 and the 404 above, the hash-seed-dependent DXF class order, and the timeout that did not cover verification.

## Licences

- New code: **not decided.** Apache-2.0 is proposed; it is not declared until the repository owner confirms it.
- Dependencies (from `uv.lock`): Shapely/GEOS (BSD-3 / LGPL-2.1 bundled library), numpy (BSD-3 and bundled terms), ezdxf (MIT), MCP SDK (MIT), Starlette/uvicorn (BSD-3), jsonschema (MIT), pydantic (MIT), certifi (MPL-2.0) and others; see `docs/IMPLEMENTATION_NOTES.md`. Test tooling: Playwright 1.63.0 (Apache-2.0), MCP Inspector 2.12.0 (MIT, not vendored).
- No code or data from the agrivoltaic planner (Apache-2.0 / CC BY 4.0), PVPlant (LGPL-2-or-later headers with no licence file) or pvlib (BSD-3) is included.
- This is a factual inventory, not legal advice.

## Next actions for Module 02 (terrain), not started

1. Accept a surveyed terrain input (TIN or DEM with its CRS and vertical datum) and keep `relative_flat_datum` results separate from terrain-fitted results by `z_kind`.
2. Fit a rack plane per table from the immutable table records, keyed by the existing `table_id` / `(i, j)`. Report slope limits and per-pile heights as new, explicitly verified quantities.
3. Add terrain-aware exclusions (slope above a limit) as additional forbidden regions, decided against the original geometry like keepouts.
4. Extend the verifier with independent terrain checks before any terrain result is persisted.
5. Re-run REA on the reference's main chunk with a larger budget only if a terrain-related reference question needs it.
