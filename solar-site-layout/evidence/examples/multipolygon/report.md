# Calculation report — res_55756be61915e4dee3504beb

Preliminary flat-site layout under the stated assumptions. It is not a construction approval, and the bounded lattice search is not a claim of a globally optimal plant design.

## Identity

- Result ID: `res_55756be61915e4dee3504beb`
- Input digest: `654c968aaf8c57397318ddb72a4654eadb8330f09e503da2b93dc3def7ff2a56`
- Numerical payload digest: `9b8b77752beb3081c8c1c59dc55914491cac31b9d90acb5d1057c9c39fd4d30b`
- Project associations: not part of this result-only report; the `context` export lists the projects and revisions that use this result.
- Algorithm `lattice-fixed-and-phase3x3/1`, geometry policy `geom-policy/1`, source commit `d935ff25e1b321dddd2d935b94134caba0bd558a`

## Frame and site

- Frame: `local_cartesian` id `local:analytic-site`
- Units: metres; x East, y North (frame north; no grid convergence correction).
- Computation frame: world translated by the anchor [1.0, 1.0] (x_local = x_world - origin_x; y_local = y_world - origin_y); no rotation or scaling of the site.
- Perimeter setback: 1.0 m from every boundary ring (outer rings and holes).
- Exclusions: none.

## Table dimensions

Module `SYNTHETIC-1x2-550`: supplied width 1.0 m (short side), length 2.0 m, 550.0 Wp, orientation **portrait**.

Oriented module: w = 1.0 m across the table, l = 2.0 m up the slope.

| Quantity | Formula | Value |
|---|---|---|
| Table width W | columns·w + (columns−1)·gap_x = 2·1.0 + 1·0.0 | 2 m |
| Slope length L | rows·l + (rows−1)·gap_y = 2·2.0 + 1·0.0 | 4 m |
| Projected depth D | L·cos(β), β = 0.0° | 4 m |
| Total rise H | L·sin(β) | 0 m |
| Lower / upper edge height | lower_edge_height, + H | 0.8 / 0.8 m |

Axes for facing azimuth A = 180.0° (clockwise from frame north): u = [1.0, 0.0], v = [0.0, 1.0] (u = (−cos A, sin A), v = (−sin A, −cos A)). Module gaps are measured in the table plane and are not part of any module.

## Placement

- Mode: `fixed_lattice`; optimality label: `fixed_lattice_no_search`.
- Anchor (world): [1.0, 1.0]. Candidate origins o(i,j) = anchor + phase + i·(W + table_gap)·u + j·row_pitch·v.
- Along-width period W + table_gap = 3 m; row pitch (lower edge to lower edge) = 5.0 m.
- Clear row gap = pitch − D = 1 m (required minimum 1.0 m).
- A table is kept only if its complete footprint is covered by the site, keeps the setback and every keepout; whole tables are dropped, modules are never cut.

## Counts and capacity

- module_count = table_count × rows × columns = 12 × 2 × 2 = **48**
- dc_capacity_kwp = module_count × module_power_wp / 1000 = 48 × 550.0 / 1000 = **26.4 kWp**
- The supplied nameplate power is the only electrical rating used. No AC capacity, voltage, current, string or inverter value is inferred.

## Areas

| Quantity | Definition | Value (m²) |
|---|---|---|
| Physical module area | module_count × supplied width × supplied length = 48 × 1.0 × 2.0 | 96 |
| Projected module area | physical × cos β | 96 |
| Table footprint area | table_count × W × D (envelope, includes module gaps) | 96 |
| Gross site area | area of the original polygon(s), holes subtracted | 336 |
| Outer-ring area | area inside outer rings, holes not subtracted (reference only) | 336 |
| Buildable area | area of the admissible region after setback and keepouts | 240 (bounds 239.993373 – 240) |

- Module ground coverage (gross) = projected module area / gross site area = 0.285714286
- Module ground coverage (buildable) = projected module area / buildable area = 0.4
- Buildable-area bounds: arcs of the setback/keepout offsets are polygonized; the lower bound uses polygons lying outside the true arcs, the upper bound chords on the arcs. Placement decisions never use this polygon: they use exact distances to the original geometry.

## Heights

`z_kind = relative_flat_datum`: z = 0 is the layout's synthetic flat datum; heights are not surveyed elevations. Module corners: z = lower_edge_height + b·sin β where b is the in-plane distance from the lower edge. These are synthetic relative heights, not surveyed elevations or terrain-fitted rack planes.

## Row pitch

The row pitch above was supplied by the user and checked only for physical overlap (pitch ≥ D) and the requested minimum clear gap (pitch ≥ D + gap). The separate 2D row-spacing estimate at a specified solar elevation (operation `calculate_row_pitch`) assumes flat ground, equal lower-edge heights, infinitely long rows and direct sun perpendicular to the rows from the facing side: recommended pitch = max(D + gap, D + H / tan α). It is not an all-year shading guarantee, an obstacle shading model or an energy-loss estimate.

## Warnings

- None.

## Rejected candidates (selected phase)

- outside_site: 24
- outside_site_untouched: 58
- perimeter_setback: 4

Exact rational re-checks of borderline distances: 8.

## Not provided by this module

Energy yield, shading losses, electrical strings, inverter selection, AC capacity, cable routing, structural checks, pile design, terrain fitting, cut/fill, code compliance and financial results.

## Provenance

- schema_version: `solar.layout.result/1`
- algorithm_version: `lattice-fixed-and-phase3x3/1`
- geometry_policy_version: `geom-policy/1`
- source_commit: `d935ff25e1b321dddd2d935b94134caba0bd558a`
- source_dirty: `False`
- created_at: `2026-10-26T11:31:25.724790Z`
- dependencies: ezdxf 1.4.5, geos 3.14.1, jsonschema 4.26.0, mcp 2.3.0, numpy 2.5.4, python 3.12.3, shapely 2.2.0, starlette 1.10.0, uvicorn 0.54.0
