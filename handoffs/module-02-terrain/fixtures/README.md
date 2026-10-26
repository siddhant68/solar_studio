# Module 02 fixtures

All lengths are metres. Table-local support coordinates (a, d) are measured along the Module 01 table axes u (width) and v (horizontal up-slope) from the table origin. Every case uses the policy `minimum_clearance_vertical_lift`:

```text
L = max over the footprint of (G(p) - d(p) tan(beta)) + minimum_clearance + structure_depth
```

All Module 01 z values of the table are raised by L − lower_edge_height_m.

| Case | Layout (Module 01) | Surface | What it pins down | Key expectation |
|---|---|---|---|---|
| T01 | rectangle (6 tables) | plane G = 100 + 0.05x + 0.10y | Planar terrain, every table placed | L = 101.15 … 101.95 m; clearance 0.5–1.0 m |
| T02 | single tilted 3-4-5 table | plane G = 50 + 0.25y | Tilt interacts with slope; the front edge governs | L = 51.0, upper edge 54.0 m; supports 0.75 / 2.25 m |
| T03 | single flat 4 × 2 table | fan with a centre vertex at 10.6 m | Hill under the middle, all corners lower | L = 11.1 m (corner-only answer 10.8 is wrong) |
| T04 | single flat 4 × 2 table | flat ring with a 1 m² hole | Void under a rack, corners surveyed | `unknown_ground`, 1.0 m² uncovered |
| T05 | rectangle | plane surveyed for x ≤ 6 | Partial survey; closed coverage edge | 4 placed, 2 `unknown_ground`; 16 modules |
| T06 | single flat 4 × 2 table | plane G = 20 + 0.6y | Support-height limit | 1.4 m > 1.2 m → `infeasible` |
| T07 | single flat 4 × 2 table | same | Slope limit | 30.96° > 25° → `infeasible` |
| T08 | — | — | Rejected inputs | Typed errors; no transformation |
| T09 | T03 rotated 30° CCW and moved to EPSG:32633 | rotated fan | Frame invariance | Same elevations as T03 |
| T10 | T03 / T01 | — | Corrupted outputs | Verifier checks that must fail |

**Layout requests.**
- `layouts/single-*.layout-request.json` are Module 01 requests whose single table lands exactly on the footprint listed in the cases. This was checked by running the accepted Module 01 (`fe15c5f`).
- The rectangle layout is `../../module-01/fixtures/rectangle.request.json`.
- The observed result IDs and payload digests are recorded per case. A different Module 01 algorithm version gives different IDs; the footprints are the contract.

**Checking.**
- `make_fixtures.py` derives the expected values from closed-form formulas with exact fractions.
- `check_fixtures.py` re-derives them from the TINs by a second route: barycentric elevations at overlay vertices, and exact footprint clipping for coverage.
- Both are standard-library scripts that check arithmetic. Neither is the terrain engine.
