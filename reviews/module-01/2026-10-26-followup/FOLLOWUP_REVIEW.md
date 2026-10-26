# Module 01 repair follow-up review

26 October 2026. PR: https://github.com/siddhant68/solar_studio/pull/1

Reviewed HEAD: `82f11f035f78b3e6daf2659582690d393b53016d`. Claimed source under acceptance: `fe15c5fda8345cbc17c2b8dc2a81fd5321fda5ef`.

**Recommendation: accept the five requested repairs and merge PR #1 as the Module 01 milestone, subject to the owner's normal merge decision. No remaining merge-blocking issue was found in this focused follow-up.** This is acceptance of the defined flat-site layout scope, not of terrain, structural/electrical design, a multi-user hosted service or an unrestricted platform release.

## Independently executed checks

- The entire supplied suite ran on macOS arm64, Python 3.12.14, using frozen Python dependencies, pinned Playwright 1.63.0 and installed Google Chrome (channel `chrome`). **233 tests passed, 0 failed, 0 skipped, 23.990 s.** This includes real process tests and the actual browser and MCP tests.
- **24/24 browser subchecks passed**, including create/update autosave delays, stale SVG, project switching/import while pending, drawing checks and no console/request/HTTP errors.
- The real MCP client transcript has **17 successful steps**.
- Reran the service/export/verifier failure probes against repaired HEAD. Natural concurrent exports: **0/24 failures**. JSON result export bytes remain unchanged after a second project reuses the same result. Deliberately falsified areas are rejected.
- Separately changed a module's power to 123456 W: rejected by `record_fields`, `record_totals` and `payload_integrity`.
- Added an independent four-process simultaneous initial bundle-publication check against one store: all four calls succeeded with identical paths and byte hashes.
- All seven recorded implementation/test/script/lock/fixture/probe tree bindings match HEAD. The numerical core files (`validation.py`, `layout.py`, `exact.py`, `result.py`) are unchanged from the reviewed implementation.

The original Linux benchmark values and reference REA pipeline were inspected as supplied evidence, not rerun here. The particular downloadable final source ZIP and Git bundle were not supplied to this review, so their published hashes were not independently checked against those files. The actual GitHub branch and exact source/evidence bindings were verified.

## Finding-by-finding assessment

| Finding | Assessment |
|---|---|
| F1 input snapshot across save | Resolved in reproduced cases. The submitted JSON is captured before awaiting save; save returns the exact snapshot and revision used. Later edits remain dirty and the older result is historical. Create/update-delay regressions both pass. |
| F2 stale drawing response | Resolved in reproduced cases. Rendering checks context/order after fetching the SVG and publishes the view without further awaits. Older SVG cannot replace the newer plan/summary/download. Context replacement cases also pass. |
| F3 parallel export collision | Resolved in reproduced cases. Unique staging, publication locking and same-handle hashed downloads replace PID-only temporary names. Same-format, mixed bundle/subformat, controlled staging, DXF and live HTTP regressions pass; independent multi-process publication also passes. |
| F4 changing result artifacts | Resolved in reproduced cases. Result exports use a versioned result-only namespace and reuse issued bytes. Project associations have their own content-addressed context artifact. Result reuse and restart leave the issued numerical exports stable. |
| F5 verifier gaps | Resolved for the reported corruptions. Record fields and totals, independently derived area checks and payload integrity now reject the altered module power and false area figures. Valid original fixtures still pass. |
| Browser 404 | Resolved in the executed browser suite. An explicit favicon route/icon is present; no error was ignored to force a pass. |

The additional DXF hash-seed regression passes in the full suite. The extended timeout check also passes. Its documented cooperative-stage behavior remains a limitation, not a strict wall-clock interrupt guarantee.

## Remaining limits and next actions

1. Merge PR #1 and tag an accepted Module 01 checkpoint when the owner is ready; keep the source archive/Git bundle outside disposable workspaces. This review did **not** merge or publish a GitHub approval/comment.
2. Add repository CI that installs pinned browser tooling and runs the suite with browser coverage required. The PR currently has no GitHub status checks. Successful local/cloud evidence is useful, but it does not substitute for future automatic regression checks.
3. Choose the new-code licence and add its text before describing a public release as Apache-2.0 or otherwise licensed. The current proposal-only wording correctly leaves the owner decision open.
4. Update the platform support notes with this exact macOS/Python/Chrome test result. It is a macOS smoke/acceptance run, not evidence for Safari, every Mac, Windows or Python 3.13+.
5. Keep the limits visible: flat synthetic datum, bounded lattice search, partial REA main-bundle static coverage, and no cross-process export locking off POSIX. The generation timeout is checked at stage boundaries and may overrun within a stage.
6. Next, write and review the terrain module contract against the accepted Module 01 output, particularly CRS/vertical datum, unknown ground, rack-plane identity and synthetic-versus-surveyed z. Do not change the accepted flat-layout result semantics while adding terrain.

## Evidence files

- `VERIFICATION.json`: exact source binding, counts and independent additional checks.
- `pytest-junit.xml`, `pytest.log`: full local suite.
- `suite/browser/ui-checks.json` and screenshots: the actual browser run.
- `suite/mcp/`: real MCP session and wire transcript.
- `adversarial-results.json`, `adversarial.log`: repeated original failure cases using the minimally adapted post-repair probe.

All evidence produced by this follow-up is outside the source repository. Application source, original review files and remote branches were left unchanged.
