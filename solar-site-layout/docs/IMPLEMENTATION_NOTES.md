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
- **`verify.py`** is the independent verifier. It recomputes axes and dimensions with its own code, checks containment, setback, keepouts and overlap with numpy vertex/segment distances and separating axes (exact fallback in the band), and runs on stored or exported records. `generate_layout` refuses to persist a result the verifier rejects (`VERIFICATION_FAILED`).
- **`store.py`**: one SQLite file in WAL mode with `BEGIN IMMEDIATE` writes; table and module records are stored one row each, keyed by `(result_id, seq)`.
- **`exports/`**: streamed writers; atomic, fsynced renames; deterministic bytes.

## Bugs found and fixed during the build

| Found | Fix |
|---|---|
| Re-exporting the same result produced a different DXF SHA-256: ezdxf stamps write time and fresh GUIDs, and its metadata dictionary holds "written by ezdxf @ timestamp". The bundle rebuild therefore invalidated the recorded DXF hash. | Fixed header metadata (`write_fixed_meta_data_for_testing` during write) and pinned ezdxf markers. A test now asserts byte-identical re-exports. |
| The first REA execution probe acted before REA armed its coverage window, so it recorded no coverage. | The probe now waits for REA's "observation armed" progress record. The empty first run is kept as evidence. |
| A keepout test of mine placed the exclusion diagonally from the table, so it was never tangent. | Corrected the test geometry; the engine was right. |
| The browser input grid let unit labels push inputs outside their column. | CSS fix. |
| Long site names were truncated in the SVG side panel. | They now wrap onto two lines. |
| `pkill -f` in a helper command matched the invoking shell. | Replaced with a PID-file server script (`scripts/dev_server.sh`). |

## Known limitations

- Only flat sites with a single metric Cartesian frame. No CRS transformation or grid convergence.
- Uniform rectangular tables and one azimuth and tilt per layout. The lattice is fixed or searched over 3×3 phases (`best_of_evaluated_candidates`, not a global optimum).
- Heights are synthetic and relative (`relative_flat_datum`).
- The row-pitch calculator covers a single elevation in a 2D, perpendicular-sun model only.
- Buildable area is polygonized with 64 segments per quarter arc and reported with bounds. Placement does not depend on it.
- Coordinate editing in the browser is JSON text. There is no drawing tool or basemap, by design.
- The SVG is meant for screen and A3-ish print. Very large sites switch to coarse scales (up to 1:200,000), where module gaps are only visible after zooming.
- Single-user local service with no authentication. HTTP binds to 127.0.0.1.
- macOS and Windows are untested (see the README).

## Dependencies (as installed from `uv.lock`) and licences

Runtime: shapely 2.2.0 (BSD-3-Clause; bundles GEOS 3.14.1, LGPL-2.1), numpy 2.5.4 (BSD-3-Clause and bundled terms), ezdxf 1.4.5 (MIT), jsonschema 4.26.0 (MIT), starlette 1.10.0 (BSD-3-Clause), uvicorn 0.54.0 (BSD-3-Clause), mcp 2.3.0 and mcp-types 2.3.0 (MIT), pydantic 2.14.1 (MIT), anyio 4.15.1 (MIT), httpx 0.28.1 (BSD-3-Clause), cryptography 50.0.2 (Apache-2.0 OR BSD-3-Clause), certifi 2026.10.23 (MPL-2.0), typing_extensions (PSF-2.0), opentelemetry-api 1.45.1 (Apache-2.0) and others as listed in `uv.lock`. Dev: pytest 9.1.1 (MIT), psutil 7.2.2 (BSD-3-Clause).

Test-time tools that are not Python dependencies: Node 22 with the preinstalled `playwright` 1.62.0 (Apache-2.0) and Chromium 153. Reference-investigation tools, kept outside this folder: rea-agents 6.8.0 (MIT) on Node 24.22.1, and @modelcontextprotocol/inspector 2.12.0 (MIT).

GEOS is LGPL-2.1 and is used as the dynamically linked library bundled in the Shapely wheel. Redistributing a wheel-based environment should keep the GEOS licence notice. This is a note, not legal advice.

## How to resume

See `CHECKPOINT.md`.
