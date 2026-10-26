# Module 02 — Terrain placement: proposal package

**Status: design proposal for owner review (26 October 2026). Not approved, not implemented.** No terrain code exists, and nothing in this folder changes Module 01.

The question Module 02 answers is: given an accepted flat-site layout and surveyed ground, at what elevation must each table stand to keep a stated clearance over its whole footprint, which tables cannot be placed and why, and how high is each stated support above ground?

| File | Content |
|---|---|
| [PLAN.md](PLAN.md) | Scope and boundaries, datums, unknown ground, the first placement operation (rigid vertical lift) and why, identity, architecture, verifier, milestones, risks |
| [CONTRACTS.md](CONTRACTS.md) | Draft surface, request and result contracts; mathematics; errors; exports |
| [contracts/](contracts/) | Draft JSON Schemas (2020-12) for the surface, the placement request and the result records |
| [ACCEPTANCE.md](ACCEPTANCE.md) | Proposed gates with numerically specified expectations |
| [fixtures/](fixtures/) | Analytic TINs, placement cases T01–T10, single-table Module 01 layout requests, and the generator and independent checker |
| [RESEARCH.md](RESEARCH.md) | What PVPlant, pvlib, PROJ, SciPy and GDAL actually do (source-read and runtime-probed), and the REA decision |
| [research/](research/) | `SOURCES.json` (commits, licences, authorities), the library probe script and its output |
| [OWNER_DECISIONS.md](OWNER_DECISIONS.md) | Decisions needed before implementation, with proposed defaults |

The fixtures use the accepted Module 01 implementation only to produce the flat layouts they start from. Footprints and observed result IDs are recorded in the cases.

Check the fixture arithmetic (standard library only):

```sh
cd handoffs/module-02-terrain/fixtures
python3 make_fixtures.py     # regenerates surfaces/ and cases/ (deterministic)
python3 check_fixtures.py    # re-derives every expected number from the TINs
```

This package depends on PR #1 (Module 01) and is independent of the CI PR. Implementation (milestone T1) starts only after the owner approves the scope and the decisions in `OWNER_DECISIONS.md`.
