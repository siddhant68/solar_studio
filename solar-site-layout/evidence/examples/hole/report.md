# Calculation report — res_0227335bfa4c9345d18675d3

Preliminary flat-site layout under the stated assumptions. It is not a construction approval, and the bounded lattice search is not a claim of a globally optimal plant design.

## Identity

- Result ID: `res_0227335bfa4c9345d18675d3`
- Input digest: `f6c78db79239e2c89183cb5f4237564ab6fcdccb5daf43836f5d432101d79556`
- Numerical payload digest: `f4797e55abc7ac4a327469572d667bc4d225381220b1393b65b3e4c50574711e`
- Project associations: not part of this result-only report; the `context` export lists the projects and revisions that use this result.
- Algorithm `lattice-fixed-and-phase3x3/1`, geometry policy `geom-policy/1`, source commit `fe15c5fda8345cbc17c2b8dc2a81fd5321fda5ef`

## Frame and site

- Frame: `local_cartesian` id `local:analytic-site`
- Units: metres; x East, y North (frame north; no grid convergence correction).
- Computation frame: world translated by the anchor [2.0, 2.0] (x_local = x_world - origin_x; y_local = y_world - origin_y); no rotation or scaling of the site.
- Perimeter setback: 0.0 m from every boundary ring (outer rings and holes).
- Exclusions: none.

## Table dimensions

Module `SYNTHETIC-1x2-550`: supplied width 2.0 m (short side), length 2.0 m, 550.0 Wp, orientation **portrait**.

Oriented module: w = 2.0 m across the table, l = 2.0 m up the slope.

| Quantity | Formula | Value |
|---|---|---|
| Table width W | columns·w + (columns−1)·gap_x = 2·2.0 + 1·0.0 | 4 m |
| Slope length L | rows·l + (rows−1)·gap_y = 2·2.0 + 1·0.0 | 4 m |
| Projected depth D | L·cos(β), β = 0.0° | 4 m |
| Total rise H | L·sin(β) | 0 m |
| Lower / upper edge height | lower_edge_height, + H | 0.8 / 0.8 m |

Axes for facing azimuth A = 180.0° (clockwise from frame north): u = [1.0, 0.0], v = [0.0, 1.0] (u = (−cos A, sin A), v = (−sin A, −cos A)). Module gaps are measured in the table plane and are not part of any module.

## Placement

- Mode: `fixed_lattice`; optimality label: `fixed_lattice_no_search`.
- Anchor (world): [2.0, 2.0]. Candidate origins o(i,j) = anchor + phase + i·(W + table_gap)·u + j·row_pitch·v.
- Along-width period W + table_gap = 6 m; row pitch (lower edge to lower edge) = 6.0 m.
- Clear row gap = pitch − D = 2 m (required minimum 2.0 m).
- A table is kept only if its complete footprint is covered by the site, keeps the setback and every keepout; whole tables are dropped, modules are never cut.

## Counts and capacity

- module_count = table_count × rows × columns = 0 × 2 × 2 = **0**
- dc_capacity_kwp = module_count × module_power_wp / 1000 = 0 × 550.0 / 1000 = **0 kWp**
- The supplied nameplate power is the only electrical rating used. No AC capacity, voltage, current, string or inverter value is inferred.

## Areas

| Quantity | Definition | Value (m²) |
|---|---|---|
| Physical module area | module_count × supplied width × supplied length = 0 × 2.0 × 2.0 | 0 |
| Projected module area | physical × cos β | 0 |
| Table footprint area | table_count × W × D (envelope, includes module gaps) | 0 |
| Gross site area | area of the original polygon(s), holes subtracted | 63.75 |
| Outer-ring area | area inside outer rings, holes not subtracted (reference only) | 64 |
| Buildable area | area of the admissible region after setback and keepouts | 63.75 (bounds 63.75 – 63.75) |

- Module ground coverage (gross) = projected module area / gross site area = 0
- Module ground coverage (buildable) = projected module area / buildable area = 0
- Buildable-area bounds: arcs of the setback/keepout offsets are polygonized; the lower bound uses polygons lying outside the true arcs, the upper bound chords on the arcs. Placement decisions never use this polygon: they use exact distances to the original geometry.

## Heights

`z_kind = relative_flat_datum`: z = 0 is the layout's synthetic flat datum; heights are not surveyed elevations. Module corners: z = lower_edge_height + b·sin β where b is the in-plane distance from the lower edge. These are synthetic relative heights, not surveyed elevations or terrain-fitted rack planes.

## Row pitch

The row pitch above was supplied by the user and checked only for physical overlap (pitch ≥ D) and the requested minimum clear gap (pitch ≥ D + gap). The separate 2D row-spacing estimate at a specified solar elevation (operation `calculate_row_pitch`) assumes flat ground, equal lower-edge heights, infinitely long rows and direct sun perpendicular to the rows from the facing side: recommended pitch = max(D + gap, D + H / tan α). It is not an all-year shading guarantee, an obstacle shading model or an energy-loss estimate.

## Warnings

- No complete table fits the admissible region; the layout is empty (zero tables, zero modules, zero capacity)

## Rejected candidates (selected phase)

- outside_site: 9
- outside_site_untouched: 16

Exact rational re-checks of borderline distances: 0.

## Not provided by this module

Energy yield, shading losses, electrical strings, inverter selection, AC capacity, cable routing, structural checks, pile design, terrain fitting, cut/fill, code compliance and financial results.

## Provenance

- schema_version: `solar.layout.result/1`
- algorithm_version: `lattice-fixed-and-phase3x3/1`
- geometry_policy_version: `geom-policy/1`
- source_commit: `fe15c5fda8345cbc17c2b8dc2a81fd5321fda5ef`
- source_dirty: `False`
- created_at: `2026-10-26T11:34:45.964847Z`
- dependencies: ezdxf 1.4.5, geos 3.14.1, jsonschema 4.26.0, mcp 2.3.0, numpy 2.5.4, python 3.12.3, shapely 2.2.0, starlette 1.10.0, uvicorn 0.54.0
