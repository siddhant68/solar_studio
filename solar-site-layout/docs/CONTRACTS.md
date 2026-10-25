# Contracts, conventions and policies (Module 01)

This file records the contracts the code implements. Where the handoff left a choice open, the decision and its reason are stated here.

## 1. Request schema `solar.layout.request/1`

JSON Schema (draft 2020-12): `src/solar_layout/schemas/solar.layout.request.v1.schema.json`.

**Fixture migration: none needed.** All handoff fixtures (`rectangle`, `obstacle`, `multipolygon`, `concave-notch`, `hole`) validate unchanged; `tests/test_validation.py::test_fixtures_are_valid_without_migration` checks this. The proposed contract was finalized with these **additions and clarifications**:

| Item | Decision |
|---|---|
| `frame.crs` | New optional field, **required** when `frame.kind = projected_cartesian`. It is kept verbatim and never used to transform anything. |
| `frame.kind` | Only `local_cartesian` and `projected_cartesian` are accepted. Anything else is `UNSUPPORTED_FRAME`. |
| `frame.units` | Must be `"m"`. A missing value is `INVALID_INPUT`; other values (including degrees) are `UNSUPPORTED_FRAME`. |
| `frame.axes` | Must be `{x: east, y: north}`, otherwise `UNSUPPORTED_FRAME`. |
| Geographic identifiers | A frame whose `id` or `crs` names a degree CRS (EPSG:4326, CRS84, WGS84, …) is `UNSUPPORTED_FRAME`, whatever its other fields say. |
| Positions | `[x, y]`. A third value is `UNSUPPORTED_INPUT` (`z_coordinate_unsupported`). |
| Rings | Must be explicitly closed (first == last) with at least 4 positions. Invalid rings are never auto-closed or repaired. |
| `module.width_m` | This is the short side, so `width_m ≤ length_m`. Otherwise the request is `INVALID_INPUT`; use `orientation` to rotate the module. |
| `placement.mode` | `fixed_lattice` or `phase_search_3x3`. |
| `table.facing_azimuth_deg` | Accepted in [−3600, 3600] and normalized to [0, 360). Equivalent values (540 and 180, for example) normalize to the same request and digest. |
| `name` | A label only. It is excluded from numerical identity. |

The row-pitch calculator has its own schema: `src/solar_layout/schemas/solar.row_pitch.request.v1.schema.json` (`solar.row_pitch.request/1`, matching the handoff fixture). Fields for solar azimuth, dates, time windows or locations are refused as `UNSUPPORTED_INPUT`.

## 2. Supported envelope and limits (typed `RESOURCE_LIMIT`)

| Limit | Value |
|---|---|
| Absolute coordinate magnitude | ≤ 10,000,000 m |
| Site bounding-box diagonal | ≤ 20,000 m |
| Module dimensions | 0.05 m to 10 m |
| Anchor distance from the site bounding box | ≤ 20,000 m (keeps the computation frame well conditioned) |
| Boundary vertices | ≤ 100,000; exclusion vertices ≤ 100,000 in total |
| Candidate table positions | ≤ 400,000 per phase and ≤ 1,200,000 per generation, checked **before** any candidate is built |
| Placed modules | ≤ 60,000, checked before modules are emitted |
| Generation time | 60 s by default (`SOLAR_LAYOUT_TIMEOUT_S`). The deadline is checked between 20,000-candidate chunks and before module generation. Exceeding it is `RESOURCE_LIMIT`, and nothing is saved. |
| HTTP body | ≤ 20 MiB |
| Page size | default 100, maximum 500. Larger requests are refused (`INVALID_CURSOR`), never truncated. |

## 3. Geometry conventions

- x is East and y is North in metres, in the declared frame. No grid-convergence correction is applied.
- **Computation frame.** World coordinates are translated by the placement anchor (`x_local = x_world − anchor_x`), with no rotation or scaling. The result stores the anchor as the inverse translation. The site is never shrunk, enlarged or buffered to make a result pass.
- Axes: `u = (−cos A, sin A)` (table width) and `v = (−sin A, −cos A)` (uphill), with A clockwise from north. Cardinal azimuths use exact 0/±1 components. `u × v = +1`, so corner order is counter-clockwise in plan.
- Oriented module: portrait `w = width_m, l = length_m`; landscape swaps them. Gaps are measured in the table plane.
- Dimensions: `W = c·w + (c−1)·gx`, `L = r·l + (r−1)·gy`, `D = L cos β`, `H = L sin β`.
- Module (row r, column c) has in-plane extents `a ∈ [c(w+gx), c(w+gx)+w]` and `b ∈ [r(l+gy), r(l+gy)+l]`. Its corners are `xy = o + a·u + b·cos β·v` and `z = lower_edge_height + b·sin β`, listed in the order c0 (a0,b0), c1 (a1,b0), c2 (a1,b1), c3 (a0,b1).
- Lattice: `o(i,j) = anchor + phase + i·(W + table_gap)·u + j·row_pitch·v`, over integer (i, j) covering the site's extent projected on u and v (padded by one index).
- Row pitch is measured lower edge to lower edge. A request is rejected (`INVALID_PITCH`) when `row_pitch < D` (physical overlap, no tolerance) or `row_pitch < D + minimum_clear_row_gap − 1e-9 m`. The pitch is never changed automatically.
- `z_kind = relative_flat_datum`: z = 0 is the layout's synthetic datum, not a surveyed elevation.

## 4. Admissibility and numerical policy (`geom-policy/1`)

A candidate table is kept only if its **complete footprint** satisfies all of the following:

1. It is covered by the original site (Polygon or MultiPolygon, holes included), using the GEOS `covers` exact predicate. Tangency to the boundary is allowed.
2. Its minimum Euclidean distance to every site boundary ring (outer rings and holes, all components) is ≥ `perimeter_setback_m`.
3. For each exclusion with `keepout_m = 0`: footprint and exclusion interiors are disjoint (GEOS `relate`, exact). Touching is allowed.
4. For each exclusion with `keepout_m > 0`: its minimum Euclidean distance to the exclusion polygon is ≥ `keepout_m`.

Distances are float GEOS values. When the float margin |d − required| is within **1e-9 m**, the decision is re-made with **exact rational arithmetic** (`exact.py`) on the coordinates as represented. Exact tangency (d == required) is therefore kept, and d = required − 2⁻⁴⁰ m is rejected. Whole tables are dropped; modules are never cut. Keepouts are true circular distances, never chord polygons; `tests/test_tolerance_and_arcs.py` builds the cases where a chord-polygon test would wrongly accept a table.

**Admissible region, used for display and buildable area only:** `site.buffer(−setback) − ∪ exclusion.buffer(keepout)`, with round joins and 64 segments per quarter circle. It never decides placement. `buildable_area_m2` is the area of that polygon. `buildable_area_bounds_m2 = [lower, upper]`: the lower bound buffers with radius `r/cos(π/256)` (a polygon outside the true arcs), and the upper bound is the chord polygon itself. For straight-edged inputs both equal the exact area.

The tolerances are kept separate:

| Tolerance | Value | Used for |
|---|---|---|
| Distance band | 1e-9 m | Triggers the exact re-check only |
| Pitch tolerance | 1e-9 m | Clear-gap requirement only |
| Verifier coordinate tolerance | 1e-6 m | Comparing records with independently re-derived positions |

Serialization uses the shortest round-trip decimal (`repr`) everywhere, and `-0.0` is written as `0.0`.

Module corners are derived from the table origin. They lie inside the checked footprint up to float rounding (≤ 1e-12 m). The checked footprint is the hull of the module extents and the W×L envelope (`footprint_checked_*` in the summary).

## 5. Phase search

Phase offsets are `(p/3·P, q/3·R)` for p, q ∈ {0, 1, 2}, evaluated in order (0,0), (0,1), …, (2,2). Table type, tilt, azimuth and pitch stay unchanged. The search selects the highest module count; a tie goes to the earliest (p, q), so phase (0,0) wins any tie it is part of. The result reports all nine scores, the selected phase, the scope, the objective, the tie-break rule and `optimality: best_of_evaluated_candidates`. Fixed-lattice requests evaluate phase (0,0) only and report `optimality: fixed_lattice_no_search`.

## 6. Identity and persistence

| Identity | Definition |
|---|---|
| `input_digest` | SHA-256 of the canonical normalized request without `name` |
| `result_id` | `res_` + `sha256(result schema \| algorithm version \| geometry policy version \| input_digest)[:24]`. It is content-addressed: the same input and policy always produce the same result ID through any interface. |
| `payload_digest` | SHA-256 over the canonical numerical summary followed by each table record and each module record. Timestamps, provenance, project sources and transport envelopes are excluded. |
| Artifact `sha256` | SHA-256 of each export file's bytes. Exports are deterministic, including the DXF, whose ezdxf timestamps and GUIDs are fixed. |

Project revisions start at 1. `update_project(expected_revision)` is a compare-and-swap inside a SQLite `BEGIN IMMEDIATE` transaction (WAL mode), so it also holds across separate processes. Every revision's request is retained.

A result and all its table and module rows are inserted in **one transaction**. A crash or injected fault leaves no result row and no partial rows. Export files are written to `*.partial`, fsynced, atomically renamed, and only then recorded. A recorded export is re-hashed before it is served.

**Selection policy:**
- Generation never edits a project's specification.
- A result generated from (project, revision) becomes the project's selection only if the project is still at that revision (compare-and-swap). Otherwise it is stored as a historical result and the newer selection is untouched.
- A selection is reported as `current` only while its source revision equals the project revision; after an edit it is reported as historical/outdated.
- Explicitly generating an old revision is allowed and always produces `historical_not_selected`.

**Browser:**
- The browser records the revision and an editor snapshot for each generate press.
- A response is labelled current only if both still match.
- Edits made while a generation is pending stay dirty.
- A response from an older press that arrives after a newer one is kept in the history and never displayed over the newer result.

## 7. Operations and transports

The operations are: `validate_request`, `calculate_row_pitch`, `create_project`, `get_project`, `update_project`, `generate_layout`, `get_layout_summary`, `get_layout_items`, `export_layout`. All three transports call the same `SolarService`.

| Operation | CLI (`solar-layout …`) | HTTP | MCP tool |
|---|---|---|---|
| validate | `validate REQ.json` | `POST /api/validate` (body: request) | `validate_request {request}` |
| row pitch | `pitch REQ.json` | `POST /api/row-pitch` (body: request) | `calculate_row_pitch {request}` |
| create project | `project create REQ.json [--name]` | `POST /api/projects {request, name?}` | `create_project {request, name?}` |
| get project | `project get ID` | `GET /api/projects/{id}` | `get_project {project_id}` |
| update project | `project update ID REQ.json --expected-revision N` | `PUT /api/projects/{id} {expected_revision, request, name?}` | `update_project {...}` |
| generate | `generate REQ.json` or `generate --project ID [--revision N]` | `POST /api/layouts {request}` or `{project_id, revision?}` | `generate_layout {...}` |
| summary | `summary RID [--project ID]` | `GET /api/layouts/{rid}[?project_id=]` | `get_layout_summary {result_id, project_id?}` |
| items | `items RID --kind modules [--offset N \| --cursor C] [--limit L]` | `GET /api/layouts/{rid}/items?kind=&offset=&cursor=&limit=` | `get_layout_items {...}` |
| export | `export RID --format F` | `POST` (create) or `GET` (download) `/api/layouts/{rid}/exports/{F}` | `export_layout {result_id, format}` |

Envelopes:
- CLI: `{"ok": true, "result": …}` with exit 0, or `{"ok": false, "error": {…}}` with exit 2.
- HTTP: the result body, or `{"error": {…}}` with the status mapped in `errors.HTTP_STATUS`.
- MCP: `CallToolResult` with `structuredContent` (and identical JSON text); errors use `isError: true` and `structuredContent = {"error": {…}}`.

The error object is the same everywhere: `{code, message, field?, details?, errors?}`. The codes are `INVALID_INPUT`, `INVALID_GEOMETRY`, `UNSUPPORTED_FRAME`, `UNSUPPORTED_INPUT`, `INVALID_PITCH`, `RESOURCE_LIMIT`, `REVISION_CONFLICT`, `PROJECT_NOT_FOUND`, `RESULT_NOT_FOUND`, `INVALID_CURSOR`, `UNSUPPORTED_OPERATION`, `VERIFICATION_FAILED` and `INTERNAL_ERROR`.

Export paths are built only from a validated result ID (`res_[0-9a-f]{24}`) and an allow-listed format, then resolved and checked to stay inside `DATA_DIR/exports`. No shell is ever invoked.

## 8. Export formats

| Format | File | Content |
|---|---|---|
| `json` | `RID-layout.json` | Normalized request, result summary, provenance, project sources, regions, all tables and modules |
| `csv` | `RID-modules.csv` | One row per module. Columns `module_id, table_id, table_i, table_j, module_row, module_column, c0_x_m, c0_y_m, c0_z_rel_m, … c3_z_rel_m, power_wp`; shortest round-trip decimals |
| `svg` | `RID-plan.svg` | Page in mm. The nested `<svg id="plan">` viewBox is in site metres at an exact 1:scale. North arrow, scale bar, legend, quantities and identity are in a side panel that never overlaps the plan. `data-x0`/`data-y1` map plan coordinates back to the world. |
| `dxf` | `RID-plan.dxf` | R2018, `$INSUNITS = 6` (m). Layers SITE_BOUNDARY, SITE_HOLES, ADMISSIBLE_REGION, KEEPOUT_ZONES, EXCLUSIONS, TABLES, MODULES, ANNOTATION. Closed LWPOLYLINEs in world coordinates, with IDs in XDATA `SOLAR_STUDIO`. |
| `report` | `RID-report.md` | Calculation report |
| `bundle` | `RID-bundle.zip` | All of the above plus `manifest.json` (result/input/payload digests, frame, versions, SHA-256 of each file) |
