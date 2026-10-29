# Module 02 — Terrain placement

**Status (29 October 2026): milestone T1 implemented on branch `feat/module-02-terrain-t1` (PR #4), not merged.** The implementation is in `solar-site-layout/src/solar_terrain/`, under the working scope in `OWNER_DECISIONS.md`. The gate results are in `solar-site-layout/reports/TERRAIN_ACCEPTANCE.json`, and the delivery report is `solar-site-layout/TERRAIN_DELIVERY_REPORT.md`. The contracts are at revision 2, with the clarifications made during implementation in `CONTRACTS.md` §10. T2–T4 remain proposals. The original design proposal (PR #3) is preserved in git history.

The question Module 02 answers is: given an accepted flat-site layout and surveyed ground, at what elevation must each table stand to keep a stated clearance over its whole footprint, which tables cannot be placed and why, and how high is each stated support above ground?

| File | Content |
|---|---|
| [PLAN.md](PLAN.md) | Scope and boundaries, datums, unknown ground, the first placement operation (rigid vertical lift) and why, identity, architecture, verifier, milestones, risks |
| [CONTRACTS.md](CONTRACTS.md) | Surface, request and result contracts (revision 2, final for T1); numerical policy; mathematics; errors; exports; implementation clarifications (§10) |
| [contracts/](contracts/) | JSON Schemas (2020-12) for the surface, the placement request and the result records; packaged byte-identically in `solar_terrain/schemas/` |
| [ACCEPTANCE.md](ACCEPTANCE.md) | Gates with numerically specified expectations (revision 2) |
| [fixtures/](fixtures/) | Analytic TINs, placement cases T01–T13, single-table Module 01 layout requests, and the generator and independent checker |
| [RESEARCH.md](RESEARCH.md) | What PVPlant, pvlib, PROJ, SciPy and GDAL actually do (source-read and runtime-probed), and the REA decision |
| [research/](research/) | `SOURCES.json` (commits, licences, authorities), the library probe script and its output |
| [OWNER_DECISIONS.md](OWNER_DECISIONS.md) | Decisions D1–D11 with defaults, and the working scope used for T1 |

The fixtures use the accepted Module 01 implementation only to produce the flat layouts they start from. Footprints and observed result IDs are recorded in the cases.

Check the package (fixture arithmetic with the standard library; schemas with jsonschema from the Module 01 environment):

```sh
cd handoffs/module-02-terrain/fixtures
python3 make_fixtures.py     # regenerates surfaces/ and cases/ (deterministic)
python3 check_fixtures.py    # re-derives every expected number from the TINs
cd .. && ../../solar-site-layout/.venv/bin/python validate_package.py   # PACKAGE_VALIDATION.json + SHA256SUMS.json
```

This package depends on PR #1 (Module 01). T1 (PR #4) contains PRs #2 and #3; the proposed merge order is #1 → #2 → #3 → #4.
