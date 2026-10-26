# Claude Cloud handoff — repair Module 01 before merge

> Historical repair brief: the five findings were repaired and accepted in the independent follow-up at `82f11f0`. For current work read [CLAUDE_NEXT_HANDOFF.md](CLAUDE_NEXT_HANDOFF.md) and [the verification report](reviews/module-01/2026-10-26-followup/FOLLOWUP_REVIEW.md).

Continue work in `siddhant68/solar_studio`, on branch **`claude/kind-cerf-gu33em`**. Fetch the current branch before editing; the latest commits include this independent review. `main` remains the original handoff. Do not start Module 02 or merge to `main` during this repair.

## Read first

1. [Independent review](reviews/module-01/2026-10-26/REVIEW.md). Findings were reproduced at implementation commit `f55f4be`.
2. [Precise repair request](reviews/module-01/2026-10-26/NEXT_ACTIONS.md).
3. [Original acceptance criteria](handoffs/module-01/ACCEPTANCE.md) and [implementation brief](handoffs/module-01/START_HERE.md).
4. [Current contracts](solar-site-layout/docs/CONTRACTS.md), [delivery report](solar-site-layout/DELIVERY_REPORT.md) and [checkpoint](solar-site-layout/CHECKPOINT.md). Treat reported passing results as historical evidence to revalidate.

The review folder contains raw observations, two browser screenshots, the test log/JUnit XML, source-tree binding checks, scripts and an integrity manifest. Its ZIP is a convenient copy of the same original review evidence. No private former checkout is needed.

## What was established

The seven implementation commits were present, and all recorded source/test/script/lock/fixture/probe tree IDs matched the reviewed implementation. On macOS Python 3.12.14, 206 supplied tests passed and one browser test skipped. Separate supplied browser checks on Chrome had 13/14 subchecks pass, with one resource-404 console failure. Additional probes exposed the five defects below. The source was left unchanged by the review.

## Required repairs

1. **P1 — input snapshot across autosave.** Generate awaits save and then snapshots live editor inputs. Editing module width from 1 m to 2 m while the save response is held can leave a 24-panel result labelled current for inputs that require 16 panels. Bind the exact submitted specification, project and revision; test both create and update response delays.
2. **P1 — stale SVG render.** Hold revision 1's SVG, fully render revision 2's 16-panel result, then release the old SVG. The old 24-panel drawing/summary/download overwrites the view while the current banner still names revision 2. Guard every asynchronous render stage and commit a coherent result view only if still current. Test project switching/imports while requests are outstanding too.
3. **P2 — concurrent export collision.** Temporary names include only PID, so HTTP worker threads share a file. Natural parallel exports failed 20/24 calls. Use uniquely created staging paths and coherent publication. Test same-format, bundle/subformat and DXF concurrency; verify returned and downloaded hashes.
4. **P2 — mutable export context.** Adding another project association changes JSON bytes at the same result/path despite unchanged numerical payload. Freeze or version the export context, preserve issued artifact identities and build bundles from one stable snapshot.
5. **P2 — verifier gaps.** A module record changed from 550 W to 123456 W is still verified, although record totals become 136.106 kWp while the summary stays 13.2 kWp. Consistently falsified area/coverage figures also pass. Verify contract-critical record fields and independent area values/bounds; reconcile totals and payload integrity.

Preserve the numerical core, existing regressions and useful REA evidence. The reference investigation has documented partial static coverage and actual runtime evidence; do not claim full main-bundle static analysis or spend this repair on unrelated REA expansion.

## Reproducing the failures

Read `browser-races.json`, `adversarial-results.json` and `additional-results.json` before running the scripts. These are **bug reproducers**, not passing tests: successful execution means observations were captured. Convert the observed failure cases into failing regression tests, then fix the implementation and make those tests pass.

Install the application using its frozen lock and use a separate scratch output directory. For `adversarial_probes.py`, set `SOLAR_REVIEW_REPO` to the absolute repository root and `SOLAR_REVIEW_OUT` to that scratch directory. Run it with the application's Python environment.

For `browser_races.cjs`, set `SOLAR_REVIEW_PLAYWRIGHT` to the installed Playwright module's absolute directory or entry point, `SOLAR_REVIEW_BASE` to your local server URL, `SOLAR_REVIEW_OUT` to the scratch directory and `SOLAR_REVIEW_CHANNEL=chromium` when using Playwright Chromium on Linux. Start the actual application server against a scratch data root. The script's Mac defaults document the original run; override them in cloud.

The source commit under review is recorded in `REVIEW_MANIFEST.json`; absolute Mac paths in old observations are provenance, not runtime dependencies. Do not overwrite committed review evidence with new runs.

## Finish criteria

- Reproduce and fix all five findings, with meaningful regressions for the real interleavings.
- Log the resource URL responsible for the browser 404, fix its cause, and rerun the real browser checks without silently dropping console failures.
- Execute the full supplied suite, added regressions, real MCP session and relevant performance/export checks on final repaired code. Browser coverage must run rather than skip unnoticed.
- Update `reports/ACCEPTANCE.json`, delivery report, checkpoint and environment/tooling instructions. Keep the original gate IDs and append/associate the new regressions; do not preserve 36/36 on obsolete evidence.
- Correct the stale claim that pushing is blocked. Reconcile the Apache-2.0 proposal/released wording and licence text without asserting an owner decision that has not been made.
- Commit and push the repairs to this branch, create a pull request into `main`, and stop before merging. Include a finding-by-finding response, exact final source commit, executed check results, remaining limitations and the PR URL.
- Regenerate a source archive/Git bundle with verified hashes. Preserve downloadable artifacts outside runtime/cache directories.

Proceed autonomously with repository-local reversible work and existing cloud tools. This task authorizes fixing and testing the module, pushing this branch and creating its PR. It does not authorize public deployment, purchases, unrelated deletions or merging. Do not stop after returning a plan.
