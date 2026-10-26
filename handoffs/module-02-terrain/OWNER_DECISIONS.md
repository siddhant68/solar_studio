# Owner decisions for Module 02

These need the owner's answer before T1 implementation starts. Each item gives the default this proposal assumes, so a reviewer can approve the defaults as a set. None of them is decided by this PR.

| # | Decision | Proposed default | Alternatives |
|---|---|---|---|
| D1 | **Approve the Module 02 scope** in `PLAN.md` §2: placement on known ground, without grading, structural or electrical design | Approve T1 as specified; T2 and T3 later | Narrow or widen T1 |
| D2 | **Terrain input for T1** | Explicit TIN JSON only; DEM in T3, LandXML in T3 | DEM first; implicit triangulation of scattered points (not recommended: it fills gaps, see the probe) |
| D3 | **Vertical datums** | Accept any declared reference (EPSG vertical CRS or named local benchmark); never transform; mismatch is an error | Add grid-based transformations later, with named grids and ballpark operations refused |
| D4 | **Partial coverage** | Uncovered tables are `unknown_ground`, reported and not placed; the rest are placed | Reject the whole request if any table is uncovered |
| D5 | **Infeasible tables** | Reported with their elevations and reasons; excluded from placed counts and capacity; the Module 01 layout is unchanged | Regenerate a reduced Module 01 layout automatically (not proposed) |
| D6 | **Placement policy and inputs** | `minimum_clearance_vertical_lift`; clearance, structure depth and both limits are required, with no defaults; no rounding of elevations | Fixed front-support height; rounding L to a construction step (e.g. 10 mm, always upward) |
| D7 | **Reorientation (tables following the ground)** | Not in T1–T3; separate approval for T4 | Include in T2 |
| D8 | **Support model** | Explicit table-local points in T1; `uniform_rows` in T2; never report "pile quantities" | Only explicit points; add vendor-specific models later |
| D9 | **Dependencies** | T1 uses the existing stack (shapely, numpy, jsonschema, ezdxf); rasterio/GDAL optional for T3 only | Make rasterio a core dependency |
| D10 | **Performance target** | TD02: 10,192 modules on 500,000 triangles in ≤ 30 s, ≤ 1 GiB on the CI runner class | Owner-specified project sizes |
| D11 | **Merge order** | PR #1 (Module 01), then the CI PR, then this proposal; each follow-up PR is retargeted to `main` after PR #1 merges | Any order the owner prefers |

Decisions outside this proposal that are still pending:
- Merge PR #1 and tag the accepted Module 01 checkpoint.
- Choose the licence for new code. Apache-2.0 is proposed but not decided.
