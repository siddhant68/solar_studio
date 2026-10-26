# Module 02 — Terrain placement: design proposal

Prepared 26 October 2026 for owner review. **This is a plan, not an implementation.** No terrain code exists, and nothing here changes Module 01. Start with `README.md` for the file map and `OWNER_DECISIONS.md` for what needs approval.

## 1. The outcome

**Given an accepted Module 01 layout and a surveyed ground surface, tell us at what absolute elevation each table must stand to keep a stated clearance over the whole of its footprint. Also say which tables cannot be placed and why, and give the height of each stated support above ground.**

A successful first milestone:
- imports a triangulated ground surface with an explicit horizontal frame and vertical datum;
- places a stored flat layout on it by rigid vertical lift;
- reports per-table elevations, clearances, slopes and coverage;
- returns per-module 3D corners and per-support above-ground heights;
- verifies all of these independently;
- exposes them through the same CLI, HTTP and MCP service as Module 01.

The flat layout and its exports stay exactly as they are.

## 2. Scope and boundaries

**In scope for the first milestone (T1):**
- One TIN per request, given as explicit vertices and counter-clockwise triangles (`solar.terrain.surface/1`). It must be in the identical metric Cartesian frame as the layout, with a declared vertical reference.
- Rigid vertical lift of whole tables under the `minimum_clearance_vertical_lift` policy.
- Clearance over the entire footprint.
- Unknown ground: footprint coverage is checked, and an uncovered table is reported, not placed.
- Ground-slope and support-height limits, with supports from an explicitly stated model.
- An independent verifier.
- Storage, paging, CLI/HTTP/MCP access, and JSON/CSV exports.

**Later milestones, each needing its own approval (section 9):**
- Supports by generated rows; DXF/SVG/report exports; a read-only browser view.
- DEM (GeoTIFF / ESRI ASCII) and LandXML import adapters.
- Reorientation: tables that tilt or roll to follow the ground. This is a different operation with a different result type (section 5.2).

**Out of scope for Module 02:**
- Grading, cut/fill and earthworks optimisation. PVPlant has an earthworks tool; we do not replicate it.
- Drainage.
- Foundation or pile design, embedment depth, total pile length and structural adequacy.
- Tracker kinematics and backtracking.
- Electrical design, energy yield and shading on terrain.
- Horizontal or vertical coordinate transformations.
- Automatic triangulation of scattered survey points.
- Interpolation or extrapolation into unsurveyed ground.

Module 02 is a placement-and-check tool for a flat-site layout on known ground. It is not a civil-engineering suite. Results are preliminary under stated assumptions and are not construction approval.

## 3. Coordinates, units and datums

### 3.1 Horizontal

- The terrain `frame` object has the same shape as Module 01's request frame (`kind`, `id`, `crs`, `units: m`, `axes: x east, y north`).
- **The terrain frame must equal the layout's frame field by field.** Otherwise the request is rejected with `FRAME_MISMATCH`. Module 02 performs no horizontal transformation, rotation or re-projection.
- A layout in `local:analytic-site` cannot be placed on a survey in `EPSG:32633`, even if someone believes they coincide. The user supplies both in one frame.
- As in Module 01, computation happens in an anchor-translated local frame for numerical conditioning, and the inverse translation is recorded. The anchor is the layout's `anchor_xy_m`.
- Fixture T09 shows that rotating and translating the whole problem gives identical elevations.

### 3.2 Vertical

- Every surface declares `vertical = {kind, crs | id, units: m, positive: up}`, where `kind` is `orthometric`, `ellipsoidal` or `local` (a named benchmark). There is no default; a missing `vertical` is `INVALID_TERRAIN`.
- A placement's elevations are expressed **in the terrain's vertical reference**, and the result's `z_kind` is `terrain_vertical_reference`. Module 01's `relative_flat_datum` heights are not surveyed elevations and are never reinterpreted as such. They are only offset (section 5.1).
- A request may assert the reference it expects (`vertical.expected_*`). If that differs from the terrain's, the request fails with `DATUM_MISMATCH`.
- **No vertical datum transformation is performed or attempted.** The library probe (`research/library-probes.json`) shows why. Offline and without the geoid grid, PROJ 9.5.1 turns WGS 84 ellipsoidal height into EGM96 height with a "ballpark" no-op: 100 m in, 100 m out, accuracy unknown (-1), and no warning or error. This held even with `only_best=True`, `PROJ_ONLY_BEST_DEFAULT=YES` and `errcheck=True`.
- A later transformation feature would have to name the grid, verify it is installed, and refuse ballpark operations. That is an owner decision, not part of this plan.

## 4. Terrain input and unknown ground

### 4.1 TIN first

The first milestone accepts only an explicit TIN: vertex coordinates plus triangles. The survey or the user decides the triangulation.

Reasons:
- The probe shows that `scipy.spatial.Delaunay` + `LinearNDInterpolator` triangulate straight across an unsurveyed interior gap and return a finite elevation there. An implicit triangulation would silently invent ground.
- PVPlant's mesh step, read at the pinned commit, shows the same risk. It also keeps degenerate zero triangles for faces it rejects.
- A TIN is the native exchange shape of survey software (LandXML `<Surface><Definition surfType="TIN">`). A later adapter can import it without changing the engine.

**Validation (`INVALID_TERRAIN`, typed field errors):**
- finite coordinates;
- at least one triangle;
- indices in range;
- counter-clockwise triangles with plan area > 1e-9 m²;
- no duplicate plan vertices;
- no two triangles overlapping in plan (a 2.5D surface);
- limits on vertex/triangle counts and coordinate magnitude, matching Module 01's envelope;
- an explicit vertical reference.

Triangles may share vertices and edges. A T-junction (a vertex lying on a neighbouring triangle's edge) is accepted only if the vertex's elevation equals that edge's interpolated elevation within 1e-9 m (decided exactly in the band). Otherwise the surface has a crack, with two elevations along one line, and is rejected.

### 4.2 DEM adapter (milestone T3)

A DEM is converted to a TIN by a stated rule:
- Valid samples sit at **pixel centres**. `AREA_OR_POINT` is honoured, and ESRI ASCII `XLLCENTER`/`XLLCORNER` are handled the way GDAL does (probe).
- Each 2 × 2 block of four valid centres becomes two triangles split on a fixed diagonal.
- A block containing any no-data sample produces no triangle.
- Reads are masked: the probe shows unmasked sampling returns the raw -9999.

The DEM's coverage is therefore the union of complete valid blocks. Nothing is filled. The DEM adapter is optional, because the rasterio wheel bundles GDAL and many libraries with their own terms.

### 4.3 Unknown ground

- **Coverage** is the closed union of the surface's triangles. A table is placed only if its whole footprint, including its boundary, lies in the coverage. Supports are inside the footprint by contract, so they are covered too.
- Otherwise the table's status is `unknown_ground` with reason `footprint_not_fully_covered`, and `covered_area_m2` and `uncovered_area_m2` are reported. It gets no elevation, no modules and no supports.
- There is no interpolation across gaps, no extrapolation beyond the edge, and no partial placement.
- A footprint ending exactly on the survey edge is covered (fixture T05).
- A void under the middle of a table makes it `unknown_ground` even when every corner is surveyed (fixture T04).
- The request field `coverage` has one allowed value in T1, `mark_unknown_ground`. Rejecting the whole request instead is a possible owner option (decision D4).

## 5. Placement

### 5.1 First operation: rigid vertical lift

Each table keeps its Module 01 XY footprint, tilt, azimuth, module grid and IDs exactly. The only change is one vertical offset per table.

Definitions, for table *t* with Module 01 axes *u*, *v*, origin *o*, projected depth *D*, tilt *β* and lower-edge height *h₀* (relative):
- *d(p) = (p − o)·v*: the horizontal up-slope distance of plan point *p* within the footprint (0 ≤ d ≤ D).
- *G(p)*: ground elevation, piecewise linear on the TIN.
- *c* = `minimum_clearance_m`, *s* = `structure_depth_m`.
- *L*: absolute elevation of the module plane's lower edge. The plane at *p* is *L + d(p)·tan β*.

Vertical clearance at *p* is

```text
C(p) = L + d(p)·tan β − s − G(p)
```

The `minimum_clearance_vertical_lift` policy chooses the smallest *L* with C(p) ≥ c everywhere on the footprint:

```text
L = max over the footprint of [ G(p) − d(p)·tan β ] + c + s
```

*G − d·tan β* is linear on each triangle, so the maximum is attained at an **overlay vertex**. Overlay vertices are:
- the footprint corners;
- TIN vertices inside the footprint;
- intersections of TIN edges with footprint edges.

The maximum is therefore exact and computable, not sampled.

Decisions within a 1e-9 m band of a limit are re-decided with exact rational arithmetic, as in Module 01. This covers coverage tangency, clearance equality and support or slope limits.

The table's vertical lift is Δ = L − h₀. Every Module 01 z value of that table (module corners, lower and upper edge) is raised by Δ. XY never changes.

**Why lift first:**
- It preserves everything Module 01 verified: footprints, setbacks, exclusions, non-overlap, counts and capacity. Only z changes, and *L* is exact.
- PVPlant's terrain adjustment illustrates the alternative. It samples only the centre line, rotates frames to follow the ground, and does not check the full footprint. That combination is how a hill under the middle of a table gets missed (fixture T03).

### 5.2 Later operation: reorientation (not in T1)

Tilting a table along its row, or changing its tilt to follow the ground, changes its 3D geometry:
- the projected footprint;
- the row spacing and inter-row clearance;
- the module corner positions;
- possibly setback and exclusion compliance.

Reorientation therefore needs:
- its own result type with re-checked plan geometry;
- an explicit fit rule (for example a least-squares plane over the footprint, with stated limits on roll and pitch);
- independent oracles (pvlib's uniform-slope formulas, `research/SOURCES.json`).

It is proposed as milestone T4, subject to owner approval (D7).

### 5.3 Clearance, slope and supports

- **Clearance** is reported per table:
  - `min_clearance_m` (equal to *c* for a placed table) and where it occurs;
  - `max_clearance_m`, the largest clearance at an overlay vertex.

  The maximum over the footprint is attained at an overlay vertex, so `max_clearance_m` is that maximum.
- **Ground slope** for a table is the steepest gradient of any triangle overlapping the footprint with positive area. A table steeper than `max_ground_slope_deg` is `infeasible` (`ground_slope_exceeds_limit`). The area-weighted mean gradient along *u* and *v* is reported as information.
- **Supports** come only from an explicit model:
  - `explicit_table_local`: a list of (a, d) table-local points;
  - in T2, `uniform_rows`: given rows and spacing.

  For each support the result gives:
  - plan position;
  - ground elevation;
  - top elevation (module plane minus *s*);
  - **above-ground height = top − ground**.

  A support above `max_support_above_ground_m` makes the table `infeasible` (`support_above_ground_exceeds_limit`).
- **What supports do not establish.** The support count follows the stated model, not dimensions or module count. Above-ground height is not embedment depth and not pile length. Foundation depth, pile quantity for procurement and structural approval need geotechnical and structural design that Module 02 does not do. Every result lists these under `not_computed`.
- **Infeasible tables** keep their computed elevation and support heights, so the problem is visible. They are excluded from placed counts and capacity (decision D5).

## 6. Identity and linkage

- **The source layout is named by `result_id` and `payload_digest` together.** The service checks both against its store (`SOURCE_MISMATCH`, `RESULT_NOT_FOUND`).
- A table or module is identified across modules by **(source result_id, payload_digest, table_id or module_id)**. `T_j0_i0` alone is unique only inside its layout. Placement records carry Module 01 IDs, and the placement summary carries the source identity.
- **Terrain identity:** `terrain_id = "ter_" + sha256(surface schema | canonical surface without name)[:24]`, plus a `terrain_digest` over the canonical content.
- **Placement identity:** `placement_id = "plc_" + sha256(placement schema | algorithm version | geometry policy | source result_id | source payload_digest | terrain_digest | canonical parameters)[:24]`. The same inputs always give the same placement through every interface.
- A **payload digest** over the canonical numerical summary and every table, module and support record works exactly as in Module 01. Exports are result-only and write-once, under a versioned path, with a separate content-addressed context file (Module 01's repaired export contract).

## 7. Architecture and integration

```text
browser / CLI / HTTP / MCP ──► SolarService ──► Module 01 engine (unchanged)
                                   │
                                   ├──► terrain validation ─► terrain engine (lift) ─► terrain verifier ─► Store
                                   │          ▲
                                   └── Module 01 records via the published record contract
```

- New package `solar_terrain` (engine, verifier, schemas). It consumes Module 01 results **only through the published contracts**: the `solar.layout.result/1` summary and the table/module record shapes, as returned by `get_layout_summary` / `get_layout_items` or found in an export. **It never imports private Module 01 modules** such as `solar_layout.layout` or `solar_layout.result` internals.
- The shared `SolarService` gains operations:
  - `validate_terrain`;
  - `import_terrain` (store a surface, immutable and content-addressed);
  - `place_on_terrain`;
  - `get_placement_summary`;
  - `get_placement_items(kind = tables | modules | supports, cursor, limit)`, paged and bounded like Module 01;
  - `export_placement(json | csv | dxf | report | bundle | context)`.
- **Persistence** adds new tables to the same SQLite store, using Module 01's transactional and write-once rules. A crash leaves no partial placement.
- **MCP tools** mirror the operations, and typed errors use the same envelope. New error codes: `INVALID_TERRAIN`, `FRAME_MISMATCH`, `DATUM_MISMATCH`, `SOURCE_MISMATCH`.
- **Provenance** records the algorithm and policy versions, source commit and dependency versions, as in Module 01.
- **CI:** the Module 01 workflow extends to the terrain suite, which runs with the same rule that browser and MCP tests are mandatory once T2 adds UI.

## 8. Independent verification

The terrain verifier is written separately from the engine and consumes records exactly as stored or exported. It checks:
1. **Source linkage.** Footprints and IDs equal the Module 01 records named by result_id + payload_digest; no table is missing or invented.
2. **Frame and datum.** The surface and summary declare identical frames and vertical references.
3. **Coverage.** It clips each footprint against every triangle with its own exact clipping, and checks covered + uncovered = footprint area and status ↔ coverage.
4. **Clearance and lift policy.** Using its own overlay vertices and barycentric evaluation (exact in the band), it checks min C ≥ c on placed tables and that the minimum is attained. That second part catches over-lifting under this policy.
5. **Module geometry.** Corners equal Module 01 corners with z + Δ.
6. **Supports.** It checks positions, ground and top elevations, above-ground heights and limits.
7. **Slope** limits and reasons.
8. **Totals and payload integrity.**

The planning fixtures already follow this approach. `fixtures/check_fixtures.py` re-derives every expected number from the TINs by a second route to the closed-form generator, and fails on planted corruptions.

## 9. Milestones

| Milestone | Delivers | Exit gates (ACCEPTANCE.md) |
|---|---|---|
| **T0 (this PR)** | Proposal, draft contracts, fixtures with independently re-derived expectations, acceptance matrix, research, owner decisions | Owner review |
| **T1** | TIN validation and storage; vertical-lift placement; coverage/unknown ground; slope and explicit-support limits; independent verifier; service, CLI, HTTP, MCP; JSON/CSV exports; CI | TR01–TR03, TC01–TC14, TV01–TV03, TS01–TS05, TD01–TD04 |
| **T2** | `uniform_rows` supports; DXF (3D faces, support points), SVG plan with elevation labels and a report; read-only browser view of a placement; browser checks | TC15, TV04, TS06 |
| **T3** | DEM adapter (GeoTIFF, ESRI ASCII) with masked reads and explicit registration; LandXML TIN import | TC16–TC17 |
| **T4 (separate approval)** | Reorientation as its own result type and verifier | Defined when approved |

Each milestone is reviewed before the next starts. A fresh agent can start T1 from this folder, Module 01's published contracts and the fixtures. No private context is needed.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Users supply terrain and layout in different frames or datums | Exact equality checks; typed mismatch errors; no transformation; documentation and fixtures T08/T09 |
| Large TINs (millions of triangles) | Spatial index per table; vertex/triangle limits with typed `RESOURCE_LIMIT`; benchmark gate TD02 |
| Survey TINs with T-junctions or slivers | Validator accepts T-junctions and rejects zero-area and overlapping triangles; borderline decisions exact |
| Expectation that supports mean pile quantities | `not_computed` list in every result; report text; acceptance gate TC11 |
| Scope creep into grading or structural design | Section 2 boundaries; owner decision D7 for reorientation; grading not planned |
