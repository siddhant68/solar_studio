# Module 02 contracts, T1 (revision 2, final for implementation)

Revision 2 replaces the draft of 26 October 2026 (PR #3). It completes the schemas, makes the numerical boundaries and the performance measurement precise, and adds fixtures; the changes are listed in section 9.

JSON Schemas (draft 2020-12, structural checks):
- `contracts/terrain-surface.schema.json`
- `contracts/placement-request.schema.json`
- `contracts/placement-result.schema.json`

Semantic rules that a schema cannot express are listed with their **enforcement point**:
- **V**: terrain/request validator.
- **E**: placement engine.
- **R**: independent result verifier, run before anything is stored and again on demand.
- **T**: tests.

Every rule has at least one point besides T.

Lengths are metres, areas m², angles degrees. Canonical JSON is Module 01's:
- UTF-8;
- sorted keys;
- separators `,` and `:`;
- floats written as Python's shortest round-trip `repr`, with -0.0 written as 0.0;
- non-finite numbers rejected.

## 1. Relationship to Module 01

- **Inputs from Module 01.** Module 02 uses only Module 01's published service operations and record shapes:
  - `get_layout_summary`: `frame`, `axes.u_table_width_axis`, `axes.v_uphill_axis`, `dimensions` (`table_width_W_m`, `table_projected_depth_D_m`, `table_rise_H_m`, `lower_edge_height_m`), `quantities.module_power_wp`, `payload_digest`, `identity`;
  - `get_layout_items` for tables and modules.

  The terrain package never imports Module 01 engine modules. Its permitted Module 01 imports are the contract utilities `solar_layout.errors` and `solar_layout.jsonio` (T: import-boundary test).
- **Identity across modules.** A table or module is identified by (source `result_id`, source `payload_digest`, `table_id`/`module_id`). Table IDs repeat between layouts.
- **No change to Module 01.** Module 01 results, payload digests and issued exports are never modified (T: TC12).

## 2. `solar.terrain.surface/1`

| Rule | Where |
|---|---|
| Structure, types, enums; `units: m`; axes east/north; `positive: up` | schema |
| `vertical.kind` orthometric/ellipsoidal ⇒ `crs` a non-empty string, no `id`; `local` ⇒ `id` a non-empty string and `crs` null or absent | schema |
| \|x\|, \|y\| ≤ 10,000,000 m; \|z\| ≤ 20,000 m | schema (bounds) and V → `RESOURCE_LIMIT` |
| At most 1,000,000 vertices and 2,000,000 triangles (T1 limits; the proposal's 2 M / 4 M is reduced until a benchmark covers it) | V → `RESOURCE_LIMIT` before any geometric work |
| Finite numbers | V (strict JSON parsing) → `INVALID_INPUT` / `INVALID_TERRAIN` |
| Triangle indices in range and distinct | V → `INVALID_TERRAIN` |
| Each triangle counter-clockwise with plan area > 1e-9 m² | V, exact (section 4) |
| No two vertices with the same (x, y) | V, exact equality of doubles |
| No two triangles whose interiors overlap in plan | V, exact predicates |
| T-junction: a vertex in the relative interior of another triangle's edge must have that edge's interpolated elevation within 1e-9 m, otherwise "crack" | V, exact |
| Coverage = closed union of the triangles; nothing implicit | E, R |

- **Identity.** `terrain_digest = sha256(canonical {"frame", "vertical", "vertices_xyz_m", "triangles"})`, where vertex coordinates are written as floats, `frame.crs` is null when absent and `vertical.crs` is null when absent. Then `terrain_id = "ter_" + sha256("solar.terrain.surface/1|" + terrain_digest)[:24]`.
- `name` and `source` are stored but excluded from identity. Vertex and triangle order are part of identity: the surface is identified as supplied.
- **Errors.** Invalid surfaces return `INVALID_TERRAIN`, with field errors such as `triangles[17]: clockwise`.

## 3. `solar.terrain.placement.request/1`

| Field | Rule | Where |
|---|---|---|
| `source_layout.result_id` + `.payload_digest` | Both required. Unknown result → `RESULT_NOT_FOUND`; digest differs from the stored result → `SOURCE_MISMATCH` | schema, V |
| `terrain` | `ter_` + 24 hex of an imported surface; unknown → `TERRAIN_NOT_FOUND` | schema, V |
| `expected_vertical` (optional) | A **complete** reference: `kind`, plus `crs` (orthometric/ellipsoidal) or `id` (local). An empty object or a reference missing its `crs`/`id` → `INVALID_INPUT`; partial assertions (kind only) are not supported. Any difference from the terrain's `kind`/`crs`/`id` → `DATUM_MISMATCH` | schema, V |
| Horizontal frame | Terrain `frame` equals the source layout's `frame` on `kind`, `id`, `crs` (absent = null), `units`, `axes` → else `FRAME_MISMATCH`. Nothing is transformed | V |
| `placement.policy` | `minimum_clearance_vertical_lift` only; other strings → `UNSUPPORTED_OPERATION` | schema accepts any string; V decides |
| `placement.minimum_clearance_m` | 0 ≤ c ≤ 20, required | schema |
| `placement.structure_depth_m` | 0 ≤ s ≤ 5, required | schema |
| `supports.model` | `explicit_table_local` only in T1 (others → `UNSUPPORTED_OPERATION`); 1–64 points (a, d) with 0 ≤ a ≤ W and 0 ≤ d ≤ D of the source layout, compared exactly as rationals, otherwise `INVALID_INPUT` | schema, V |
| `limits.max_ground_slope_deg` | 0 < x ≤ 60 | schema |
| `limits.max_support_above_ground_m` | 0 < x ≤ 20 | schema |
| `coverage` | `mark_unknown_ground` | schema |

**Identity:**
- `parameters_digest = sha256(canonical {"placement", "supports", "limits", "coverage", "expected_vertical"})`, with `expected_vertical` null when absent.
- `placement_id = "plc_" + sha256("solar.terrain.placement.result/1|" + algorithm_version + "|" + policy_version + "|" + result_id + "|" + payload_digest + "|" + terrain_digest + "|" + parameters_digest)[:24]`.
- `algorithm_version = "terrain-vertical-lift/1"` and `policy_version = "terrain-policy/1"`.

## 4. Numerical policy `terrain-policy/1`

All decisions use the represented double values of the inputs: vertex coordinates, Module 01 footprint corners, W, D, H, a, d, c, s and the limits. Computation uses an anchor-translated frame (the layout's `anchor_xy_m`). There are three separate kinds of comparison.

### 4.1 Position and incidence (m): exact, no tolerance

Exact predicates (floating-point filter with a certified error bound, otherwise exact rational arithmetic):
- orientation of three points;
- point in closed triangle;
- segment meeting an open convex polygon;
- triangle interiors overlapping;
- triangle interior meeting a footprint interior.

These decide:
- triangle orientation;
- plan overlap;
- T-junction incidence;
- **coverage**;
- which triangles count for slope;
- point location.

There is no distance tolerance, so a survey gap of any positive width under a footprint makes it `unknown_ground`. A footprint edge lying exactly on the survey boundary is covered.

**Coverage (E)** follows from the topology:
- *Boundary segments* are triangle edges split at T-junction vertices that have no oppositely directed twin.
- The closed footprint F lies in the coverage U if and only if no boundary segment meets the open interior of F and the centroid of F lies in U.

**Coverage (R)** reconstructs its own boundary segments from the candidate triangles and applies the same mathematical criterion with its own exact code. It also checks that the clipped areas add up (section 4.2).

### 4.2 Areas (m²): reported, never used to decide status

- `covered_area_m2` and `uncovered_area_m2` are double-precision sums of clipped triangle areas. They are informative.
- R checks covered + uncovered = footprint area within 1e-9 · max(1, area). It also checks that `unknown_ground` ⇔ the exact coverage test fails, whatever the reported areas.
- The triangle degeneracy rule (plan area > 1e-9 m²) is decided exactly on the rational area.

### 4.3 Elevations (m): computed in double, limits decided exactly in a band

- *L*, clearances, support tops, ground elevations and above-ground heights are double-precision values from the translated frame. R recomputes them independently and agrees within **1e-9 m**.
- The support-height limit is the only elevation **decision**. If |height − limit| ≤ 1e-9 m, E recomputes that table's *L* and the height exactly in rationals. It then decides strictly: height > limit exceeds; equality is within the limit.
- T-junction consistency (|z_M − z_interpolated| ≤ 1e-9 m) is decided exactly.

### 4.4 Slopes: decided on the gradient, reported as an angle

- A triangle's gradient magnitude g is a rational function of its vertices. g² is compared exactly with t², where t = `math.tan(math.radians(limit))` evaluated in IEEE double (a documented, deterministic constant per limit).
- "Exceeds" means g² > t² over any triangle whose interior meets the open footprint (section 4.1).
- The reported `max_ground_slope_deg = degrees(atan(g))` is an informative double. Its last-digit agreement with the decision is not claimed: the decision is on g² vs t², and the angle's error is ≈1e-13°.
- **Not claimed:** that the angle is exact because the coordinates are rational, or that `math.tan` is correctly rounded on every platform. A limit whose t lies within a few ulps of a triangle's g can decide differently with a different libm.

### 4.5 Ties and shared edges

- **Point location** (corners, supports, centroid) uses the lowest-index triangle in the surface whose closed area contains the point. Crack-free surfaces give the same elevation from any containing triangle, within the 1e-9 m T-junction allowance.
- **Overlay values**:
  - a TIN vertex inside F uses its own z;
  - a TIN-edge ∩ footprint-edge point uses linear interpolation along that triangle edge;
  - a footprint corner uses point location.
- **`min_clearance_at_xy_m`** is the overlay point with the largest G − d·tan β. Ties on equal double values are broken by the smallest table-local d, then the smallest a.

## 5. Mathematics (policy `minimum_clearance_vertical_lift`)

The footprint F is the Module 01 table record's `footprint_xy_m` polygon: corners c₀ (origin), c₁ (c₀ + W·u), c₂ and c₃ (c₀ + D·v).

The quantities below use:
- u, v: the summary axes;
- tan β = H / D, or 0 when H = 0;
- d(p) = (p − c₀)·v;
- h₀ = `lower_edge_height_m`;
- c, s: clearance and structure depth.

| Quantity | Definition |
|---|---|
| G(p) | Barycentric interpolation in the located triangle |
| L (lower edge) | max over overlay points of (G − d·tan β) + c + s. Overlay points are the corners of F, TIN vertices in closed F, and intersections of candidate-triangle edges with F's edges |
| Upper edge | L + D·tan β |
| Vertical lift Δ | L − h₀. Every Module 01 z of the table is raised by Δ; x and y are unchanged |
| Clearance at p | L + d(p)·tan β − s − G(p); `min_clearance_m` and `max_clearance_m` over overlay points |
| Support position | c₀ + (a/W)(c₁ − c₀) + (d/D)(c₃ − c₀) |
| Support top | L + d·tan β − s |
| Above-ground height | top − G(support) |
| Slope set | Triangles whose interior meets F's interior |
| `max_ground_slope_deg` | degrees(atan(max g)) over the slope set |
| `mean_ground_gradient_uv` | Area-weighted mean of (∇G·u, ∇G·v) over F ∩ triangles (informative) |

**Status:**
- Coverage test fails → `unknown_ground`.
- Otherwise any limit exceeded → `infeasible`, with reasons in the order `ground_slope_exceeds_limit`, `support_above_ground_exceeds_limit`.
- Otherwise → `placed`.

## 6. `solar.terrain.placement.result/1`

**Summary (schema-required):**
- `schema_version`, `placement_id`;
- `source_layout` {`result_id`, `payload_digest`, `schema_version`, `algorithm_version`};
- `terrain` {`terrain_id`, `terrain_digest`};
- `parameters_digest`;
- `frame`, `vertical` (both copied from the terrain);
- `z_kind: terrain_vertical_reference`;
- `policy` {`policy`, `minimum_clearance_m`, `structure_depth_m`, `supports_model`, `limits`, `coverage`, `numerical_policy: terrain-policy/1`};
- `counts`;
- `statistics`;
- `diagnostics` (candidate counts, exact fallbacks);
- `warnings`;
- `not_computed`: exactly `["embedment_depth", "pile_length", "foundation_design", "structural_adequacy", "grading", "cut_fill", "drainage"]`;
- `provenance` {`algorithm_version`, `policy_version`, `schema_version`, `software_version`, `source_commit`, `source_tree_dirty`, `dependencies`, `created_at`};
- `verification` {`ok`, `checks`};
- `payload_digest`.

**Counts.** These are schema-constrained non-negative integers. R checks the relations:
- `tables` = placed + unknown_ground + infeasible;
- `placed_modules` = Σ module_count of placed tables;
- `placed_dc_capacity_kwp` = Σ `power_wp` of placed modules / 1000;
- `supports` = number of support records.

### Table records (schema `oneOf` by status)

| Status | Required | Forbidden |
|---|---|---|
| `placed` | `lower_edge_z_m`, `upper_edge_z_m`, `vertical_lift_m`, `min_clearance_m`, `min_clearance_at_xy_m`, `max_clearance_m`, `max_ground_slope_deg`, `mean_ground_gradient_uv`; `reasons` = [] | — |
| `infeasible` | The same measurements; `reasons` non-empty, from the two limit reasons | — |
| `unknown_ground` | `reasons` = [`footprint_not_fully_covered`]; `uncovered_area_m2` > 0 | Every elevation, clearance, slope and gradient field |

All statuses also carry `seq`, `table_id`, `module_count`, `footprint_xy_m`, `covered_area_m2` and `uncovered_area_m2`.

### Module and support records

**Module records** (placed tables only — R): `seq`, `module_id`, `table_id`, `corners_xyz_m`.

**Support records** (placed and infeasible tables — R): `seq`, `support_id` (`S_<table_id>_<k>`), `table_id`, `a_m`, `d_m`, `xy_m`, `ground_z_m`, `top_z_m`, `above_ground_m`. No module or support record exists for an `unknown_ground` table.

**Payload digest.** SHA-256 over:
1. the canonical summary subset {`schema_version`, `placement_id`, `source_layout`, `terrain`, `parameters_digest`, `frame`, `vertical`, `z_kind`, `policy`, `counts`};
2. then each table, module and support record, each preceded by `\n`.

Records are canonical JSON, in Module 01 table order, then module order, then support order.

## 7. Errors

All errors use Module 01's envelope and codes, plus these:

| Code | When | HTTP |
|---|---|---|
| `INVALID_TERRAIN` | Surface fails validation | 422 |
| `TERRAIN_NOT_FOUND` | Unknown `ter_…` | 404 |
| `PLACEMENT_NOT_FOUND` | Unknown `plc_…` | 404 |
| `FRAME_MISMATCH` | Terrain frame ≠ layout frame | 422 |
| `DATUM_MISMATCH` | `expected_vertical` ≠ terrain vertical reference | 422 |
| `SOURCE_MISMATCH` | `payload_digest` ≠ stored result's | 409 |
| `RESOURCE_LIMIT` | Count, magnitude or time limits (`SOLAR_TERRAIN_TIMEOUT_S`, default 300 s) | 413 |
| `VERIFICATION_FAILED` | R rejects the engine's result; nothing is stored | 500 |

## 8. Persistence and exports

**Persistence:**
- Terrains, placements and their records live in `DATA_DIR/terrain.sqlite3`, beside Module 01's database, which is not modified.
- Each import or placement is one `BEGIN IMMEDIATE` transaction, so an interrupted write leaves nothing.
- Terrains and placements are immutable and content-addressed; repeating an import or placement reuses the stored row.

**Exports** of a placement are written under `DATA_DIR/terrain-exports/<placement_id>/v1/`:
- `json`: `solar.terrain.placement.export/1`, the full summary and all records.
- `csv`: one row per module of a placed table, with absolute corners.
- `supports_csv`: one row per support.

They are result-only, write-once (unique staging, publication lock, re-hashed on reuse, refused if an issued file would change), and byte-identical in any process.

## 9. Changes from the draft

1. **Result schema completed.**
   - Required provenance and verification were added, plus an exact `not_computed` list.
   - Table records became status-dependent (`oneOf`); `unknown_ground` forbids elevations.
   - Counts, IDs and digests are constrained, and the semantic count relations are assigned to R.
2. **Expected-datum assertion made precise.** The field is renamed `expected_vertical`, must be complete, and partial or empty assertions are rejected.
3. **New error codes:** `TERRAIN_NOT_FOUND`, `PLACEMENT_NOT_FOUND`.
4. **Numerical policy split** into position/incidence (exact), area (informative) and elevation (double, with an exact band at the support limit), plus a slope decision on g² vs t². Ties, shared edges and point location are now deterministic.
5. **Coverage defined topologically and exactly.** A micro-gap fixture (T11) was added.
6. **T1 limits** reduced to 1 M vertices / 2 M triangles; `terrain` must be a stored ID; `supports.model` beyond explicit points is rejected in T1.
7. **Performance measurement defined** (PLAN.md §11). Bounded candidate selection is required in both the engine and the verifier.
