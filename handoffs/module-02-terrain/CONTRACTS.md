# Module 02 draft contracts (for review)

JSON Schemas: `contracts/terrain-surface.schema.json`, `contracts/placement-request.schema.json` and `contracts/placement-result.schema.json` (draft 2020-12). The schemas check structure. The rules below are semantic and are enforced by the validator and the verifier. All lengths are metres and all angles are degrees. Floats are serialized as the shortest round-trip decimal, as in Module 01.

## 1. Relationship to Module 01

- **Inputs from Module 01.** Module 02 consumes only the published contracts: the `solar.layout.result/1` summary (frame, axes, dimensions, identity) and the table and module records. A table record has `table_id`, `i`, `j`, `origin_xy_m`, `footprint_xy_m`, `lower_edge_z_m`, `upper_edge_z_m` and `module_count`. A module record has `module_id`, `table_id`, `row`, `column` and `corners_xyz_m`.
- **Identity across modules.** A table or module is identified by the triple (source `result_id`, source `payload_digest`, `table_id`/`module_id`).
- **No change to Module 01.** Module 01 results, their payload digests and their exports are never modified.

## 2. `solar.terrain.surface/1`

| Field | Rule |
|---|---|
| `frame` | Same object shape as the Module 01 request frame |
| `vertical.kind` | `orthometric`, `ellipsoidal` or `local` |
| `vertical.crs` | Required for orthometric/ellipsoidal (e.g. `EPSG:5773`); `null` for local |
| `vertical.id` | Required for local (e.g. `local:site-benchmark-A`) |
| `vertical.units`, `vertical.positive` | `m`, `up` |
| `vertices_xyz_m` | Finite; \|x\|, \|y\| ≤ 10,000,000 m; \|z\| ≤ 20,000 m; at most 2,000,000 vertices (proposed limit) |
| `triangles` | Indices in range; counter-clockwise in plan; plan area > 1e-9 m²; at most 4,000,000 triangles (proposed limit) |
| Plan uniqueness | No two vertices share a plan position; no two triangles overlap in plan with positive area; a vertex lying on another triangle's edge (T-junction) must have that edge's interpolated elevation within 1e-9 m, otherwise the surface has a crack and is rejected |
| Coverage | Exactly the closed union of the triangles; there is no implicit triangulation, filling or extrapolation |

Validation failures are `INVALID_TERRAIN` with field errors, for example `triangles[17]: clockwise` or `vertices_xyz_m[4][2]: not finite`.

- **Terrain identity:** `terrain_digest = sha256(canonical JSON of {frame, vertical, vertices_xyz_m, triangles})` and `terrain_id = "ter_" + sha256("solar.terrain.surface/1|" + terrain_digest)[:24]`. The name and source metadata are stored but excluded from identity.

## 3. `solar.terrain.placement.request/1`

| Field | Rule |
|---|---|
| `source_layout.result_id`, `.payload_digest` | Both must match a stored Module 01 result (`RESULT_NOT_FOUND`, `SOURCE_MISMATCH`) |
| `terrain` | A stored `ter_…` ID |
| `vertical` (optional) | Expected vertical reference; any difference is `DATUM_MISMATCH` |
| `placement.policy` | `minimum_clearance_vertical_lift` only; others are `UNSUPPORTED_OPERATION` |
| `placement.minimum_clearance_m` | 0 ≤ c ≤ 20; required, no default |
| `placement.structure_depth_m` | 0 ≤ s ≤ 5; required |
| `supports` | `explicit_table_local` (points (a, d) with 0 ≤ a ≤ W, 0 ≤ d ≤ D, otherwise `INVALID_INPUT`) or, from T2, `uniform_rows` |
| `limits.max_ground_slope_deg` | (0, 60] |
| `limits.max_support_above_ground_m` | (0, 20] |
| `coverage` | `mark_unknown_ground` only in T1 |

**Frame rule.** The terrain frame must equal the layout's request frame on `kind`, `id`, `crs`, `units` and `axes`, otherwise `FRAME_MISMATCH`. Nothing is transformed.

**Placement identity.** `parameters_digest = sha256(canonical {placement, supports, limits, coverage, vertical})`. The placement ID is `placement_id = "plc_" + sha256("solar.terrain.placement.result/1|" + algorithm_version + "|" + geometry_policy_version + "|" + result_id + "|" + payload_digest + "|" + terrain_digest + "|" + parameters_digest)[:24]`.

## 4. Mathematics (policy `minimum_clearance_vertical_lift`)

The quantities used below:
- *u*, *v*: the table's width and up-slope axes, from the Module 01 summary.
- *o*: the table's `origin_xy_m`.
- *W* and *D*: the table's width and projected depth.
- *tan β* = H / D, where H is the rise (0 when the table is flat).
- *h₀*: Module 01 `lower_edge_height_m`.
- Table-local coordinates of a plan point *p*: *a = (p − o)·u* and *d = (p − o)·v*.

| Quantity | Definition |
|---|---|
| Ground *G(p)* | Barycentric interpolation in the (unique) covering triangle |
| Module plane | *L + d(p)·tan β* |
| Clearance *C(p)* | *L + d(p)·tan β − s − G(p)* |
| Lower edge *L* | *max over footprint of (G(p) − d(p)·tan β) + c + s*, attained at an overlay vertex: footprint corners, TIN vertices inside the footprint, TIN-edge × footprint-edge intersections |
| Upper edge | *L + D·tan β* |
| Vertical lift Δ | *L − h₀*; every Module 01 z of the table + Δ; x and y unchanged |
| Support position | *o + a·u + d·v* |
| Support top | *L + d·tan β − s* |
| Support above-ground height | top − *G* at the support position |
| Ground slope | max over triangles overlapping the footprint with positive area of atan(\|∇G\|) |
| Mean ground gradient (informative) | area-weighted mean of ∇G·u and ∇G·v over the footprint |

**Status rules:**
- Not fully covered → `unknown_ground`, with reason `footprint_not_fully_covered` and no elevations.
- Covered and any limit exceeded → `infeasible`, with reasons in the order `ground_slope_exceeds_limit`, `support_above_ground_exceeds_limit`. The table keeps its computed elevations for inspection.
- Otherwise → `placed`.

**Numerical policy (`terrain-policy/1`, proposed):**
- Computation is in the anchor-translated frame.
- A float margin within 1e-9 m (or 1e-12 relative for areas) of a decision boundary is re-decided exactly with rational arithmetic on the represented coordinates. Decision boundaries are coverage tangency, clearance equality, support-in-footprint, and slope or height limits.
- Verification tolerances are 1e-6 m for coordinates (as in Module 01) and 1e-9 m for elevations in analytic fixtures.

## 5. `solar.terrain.placement.result/1`

**Summary:**
- `placement_id`;
- `source_layout` {`result_id`, `payload_digest`, `schema_version`, `algorithm_version`};
- `terrain` {`terrain_id`, `terrain_digest`};
- `parameters_digest`;
- `frame` and `vertical`, copied from the terrain;
- `z_kind: terrain_vertical_reference`;
- `policy`, containing parameters and limits;
- `counts`: tables by status, `placed_modules`, `placed_dc_capacity_kwp` (placed module count × module power from the source records) and `supports`;
- clearance and slope statistics;
- `warnings`;
- `not_computed`, which always lists: embedment depth, pile length, foundation design, structural adequacy, grading, cut/fill, drainage;
- `payload_digest`;
- provenance.

**Records**, paged with `kind = tables | modules | supports`, in Module 01 table order, then module order, then support order:
- **tables:** one per source table, in every status. Each record gives status, reasons, the footprint (copied), covered/uncovered area, and L, upper edge, Δ, minimum clearance and its location, maximum clearance, maximum slope and mean gradient where computed.
- **modules:** placed tables only. Each record gives the Module 01 IDs and the absolute `corners_xyz_m`.
- **supports:** placed and infeasible tables. Each record gives `support_id = S_<table_id>_<k>`, a, d, xy, ground z, top z and above-ground height.

**Payload digest.** SHA-256 over the canonical numerical summary, then every table, module and support record, as in Module 01.

## 6. Errors

All errors use Module 01's codes and envelope, plus four new codes:

| Code | When | HTTP |
|---|---|---|
| `INVALID_TERRAIN` | Surface fails validation (including a missing vertical reference) | 422 |
| `FRAME_MISMATCH` | Terrain frame differs from the layout frame | 422 |
| `DATUM_MISMATCH` | Expected vertical reference differs from the terrain's | 422 |
| `SOURCE_MISMATCH` | `payload_digest` does not match the stored `result_id` | 409 |

## 7. Exports (T1: json, csv; T2: dxf, report, bundle)

Exports follow the repaired Module 01 contract:
- result-only and write-once under `PLC/v1/`;
- a separate content-addressed `context` file that names the source layout and terrain;
- byte-identical in every process.

The CSV has one row per module of a placed table, with absolute corner elevations. A second CSV has one row per support. In T2 the DXF uses 3DFACE entities for modules and the TIN within the layout extent, and POINT entities for supports, with layers and IDs in XDATA.
