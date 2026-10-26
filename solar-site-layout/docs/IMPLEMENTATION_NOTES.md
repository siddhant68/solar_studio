# Implementation notes

## Architecture as built

```text
browser (web/app.js) ─HTTP─┐
CLI (cli.py) ──────────────┼──► SolarService (service.py) ──► validation ─► layout engine ─► ResultRecords ─► verifier ─► Store (SQLite)
MCP stdio (mcp_server.py) ─┘                                                                                                  │
                                                                                                                exports (json/csv/svg/dxf/report/bundle)
```

- **`validation.py`** applies the JSON Schema (structure), then frame semantics, per-ring geometry (closed, ≥ 4 positions, GEOS validity, non-zero area), the supported envelope and pitch feasibility. It returns a normalized request plus local (anchor-translated) Shapely geometry.
- **`layout.py`** projects the site onto (u, v) to bound the lattice indices, builds candidate footprints in 20,000-row chunks with numpy and decides admissibility with vectorized GEOS predicates. Borderline distance margins go to `exact.py` (`fractions.Fraction`). Running the 3×3 phase search is simply nine evaluations.
- **`result.py`** produces world-coordinate records, deterministic IDs (`T_j{j}_i{i}`, `T_j{j}_i{i}_r{r}_c{c}`), the canonical payload digest and the result ID.
- **`verify.py`** is the independent verifier. It recomputes axes and dimensions with its own code, checks containment, setback, keepouts and overlap with numpy vertex/segment distances and separating axes (exact fallback in the band), checks every contract field of every record, reconciles record totals with the summary, recomputes the areas (shoelace; buildable area bracketed by its own construction) and the payload digest, and runs on stored or exported records. `generate_layout` refuses to persist a result the verifier rejects (`VERIFICATION_FAILED`).
- **`store.py`**: one SQLite file in WAL mode with `BEGIN IMMEDIATE` writes; table and module records are stored one row each, keyed by `(result_id, seq)`.
- **`exports/`**: streamed writers; unique staging files, fsync and atomic rename under a per-(result, format) lock; write-once records; result-only content (project associations go to the separate `context` export); byte-identical in any process.

## Bugs found and fixed during the build

| Found | Fix |
|---|---|
| Re-exporting the same result produced a different DXF SHA-256: ezdxf stamps write time and fresh GUIDs, and its metadata dictionary holds "written by ezdxf @ timestamp". The bundle rebuild therefore invalidated the recorded DXF hash. | Fixed header metadata (`write_fixed_meta_data_for_testing` during write) and pinned ezdxf markers. A test now asserts byte-identical re-exports. |
| The first REA execution probe acted before REA armed its coverage window, so it recorded no coverage. | The probe now waits for REA's "observation armed" progress record. The empty first run is kept as evidence. |
| A keepout test of mine placed the exclusion diagonally from the table, so it was never tangent. | Corrected the test geometry; the engine was right. |
| The browser input grid let unit labels push inputs outside their column. | CSS fix. |
| Long site names were truncated in the SVG side panel. | They now wrap onto two lines. |
| `pkill -f` in a helper command matched the invoking shell. | Replaced with a PID-file server script (`scripts/dev_server.sh`). |

## Review repair (independent review of 26 October 2026)

The review in `../reviews/module-01/2026-10-26/` reproduced five defects at `f55f4be`. Each was reproduced again here before the fix (`evidence/repair/before/`), turned into a failing regression, then fixed (`evidence/repair/after/`). The numerical core (validation, layout engine, exact kernel, result records) is unchanged.

| Finding | Root cause | Fix | Regressions |
|---|---|---|---|
| F1 (P1) input snapshot across autosave | `generate()` awaited `save()` and only then read the editor, so an edit made while the save was in flight was recorded as the inputs of a result computed from the saved revision; it was labelled current. | The snapshot is taken synchronously when Generate is pressed, and `save(snapshot)` saves exactly that JSON. Saves are queued, each naming the revision returned by the previous one. Results carry the project ID, revision and snapshot; "current" requires all three to match. | Browser V02 "F1 create-delay" (project POST held) and "F1 update-delay" (PUT held) |
| F2 (P1) stale SVG render | `display()` set the displayed entry, then awaited the plan SVG and rendered whatever arrived, with no freshness check after the await. | Rendering happens only after the last await, and only if the entry is still the newest generation (`seq`) of the current editing context (`viewEpoch`). Opening a project, importing a file or loading an example starts a new context and clears the view; discarded responses are listed in the session history. | Browser V02 "F2 stale SVG", "project switch", "import while pending" |
| F3 (P2) concurrent export collision | The staging name contained only the PID, so HTTP worker threads shared one temporary file; the first rename left the others failing (`FileNotFoundError`). DXF writing also flipped a process-wide ezdxf option. | `tempfile.mkstemp` staging per build; per-(result, format) publication lock (thread lock plus `flock`); downloads stream from the handle whose bytes were hashed; DXF metadata fixed on the document instance only. | `test_f3_*` in `tests/test_review_regressions.py`: 24 parallel service exports per format, a controlled overlap inside the staging write, DXF concurrency without touching the global option, live-server parallel downloads with bundle/subformat overlap and header/body/manifest hash agreement |
| F4 (P2) mutable export context | JSON, SVG and report embedded the result's project sources, which grow when another project reuses the result, so the same path was rewritten with different bytes. | Result exports contain the result only, live under a versioned path (`RID/v2/`) and are write-once. Project associations are a separate content-addressed `context` export. The bundle is built from one row snapshot and re-hashes each part as it copies it. | `test_f4_*`: reuse by a second project and revision plus a service restart leaves all six result exports byte-identical; context files are new and old ones are kept; reuse keeps the same inode; bundle manifest equals the standalone hashes |
| F5 (P2) verifier gaps | The verifier derived capacity from the request and module count, never read per-record power, and trusted the reported area denominators. | New checks `record_fields`, `record_totals`, `areas` and `payload_integrity` (see CONTRACTS §6). The geometric checks are unchanged and still independent of the generator. | `test_f5_*`: 123,456 W module, all modules 600 W, consistently falsified gross/buildable areas and ratios, buildable area inside gross with self-consistent bounds, corrupted IDs and lattice fields, corrupted table records, zeroed payload digest; all fixtures still verify |
| Browser 404 | The page had no icon, so full Chromium requested `/favicon.ico`, which had no route (the headless shell does not request it, which is why the build-session checks missed it). | `/static/favicon.svg` linked from the page, and a `/favicon.ico` route. The browser checks now launch full Chromium and log the URL of every console error, failed request and HTTP status ≥ 400. | Every "no browser errors" check |

Found during the repair: **DXF bytes depended on `PYTHONHASHSEED`.** ezdxf writes a CLASS definition for each entity type in use while iterating a `set` of type names, so the CLASSES section order (and the DXF and bundle hashes) differed between processes; re-exports agreed only within one process. The document's entity database now reports those types sorted. `test_exports_identical_across_processes_and_hash_seeds` exports one stored result under three hash seeds. Earlier DXF/bundle hashes in old evidence remain valid for the bytes they describe but are not reproducible in every process.

## Known limitations

- Only flat sites with a single metric Cartesian frame. No CRS transformation or grid convergence.
- Uniform rectangular tables and one azimuth and tilt per layout. The lattice is fixed or searched over 3×3 phases (`best_of_evaluated_candidates`, not a global optimum).
- Heights are synthetic and relative (`relative_flat_datum`).
- The row-pitch calculator covers a single elevation in a 2D, perpendicular-sun model only.
- Buildable area is polygonized with 64 segments per quarter arc and reported with bounds. Placement does not depend on it.
- Coordinate editing in the browser is JSON text. There is no drawing tool or basemap, by design.
- The SVG is meant for screen and A3-ish print. Very large sites switch to coarse scales (up to 1:200,000), where module gaps are only visible after zooming.
- Single-user local service with no authentication. HTTP binds to 127.0.0.1.
- macOS and Windows are untested (see the README). Off POSIX, export publication is serialized within one process only (no `flock`).

## Dependencies (as installed from `uv.lock`) and licences

Runtime: shapely 2.2.0 (BSD-3-Clause; bundles GEOS 3.14.1, LGPL-2.1), numpy 2.5.4 (BSD-3-Clause and bundled terms), ezdxf 1.4.5 (MIT), jsonschema 4.26.0 (MIT), starlette 1.10.0 (BSD-3-Clause), uvicorn 0.54.0 (BSD-3-Clause), mcp 2.3.0 and mcp-types 2.3.0 (MIT), pydantic 2.14.1 (MIT), anyio 4.15.1 (MIT), httpx 0.28.1 (BSD-3-Clause), cryptography 50.0.2 (Apache-2.0 OR BSD-3-Clause), certifi 2026.10.23 (MPL-2.0), typing_extensions (PSF-2.0), opentelemetry-api 1.45.1 (Apache-2.0) and others as listed in `uv.lock`. Dev: pytest 9.1.1 (MIT), psutil 7.2.2 (BSD-3-Clause).

Test-time tools that are not Python dependencies: Node ≥ 20 (22 used here) with `playwright` 1.63.0 (Apache-2.0), pinned with integrity hashes in `tests/browser/package-lock.json` and installed by `scripts/bootstrap_browser.sh`, and its Chromium 153 build. Reference-investigation tools, kept outside this folder: rea-agents 6.8.0 (MIT) on Node 24.22.1, and @modelcontextprotocol/inspector 2.12.0 (MIT).

GEOS is LGPL-2.1 and is used as the dynamically linked library bundled in the Shapely wheel. Redistributing a wheel-based environment should keep the GEOS licence notice. This is a note, not legal advice.

## How to resume

See `CHECKPOINT.md`.
