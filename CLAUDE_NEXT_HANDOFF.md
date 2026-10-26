# Claude Cloud continuation — verified Module 01, CI and terrain planning

Repository: `siddhant68/solar_studio`. Prepared 26 October 2026.

## Current state and assignment

The five Module 01 review findings have been repaired and independently rechecked. The
independent reports were previously available only on the reviewer's Mac; they are now
committed under `reviews/module-01/2026-10-26-followup/`, including the raw evidence and
a portable reproduction script. Read them through Git; no Mac filesystem access is needed.

Your next work is:

1. Incorporate the independent verification into project status and documentation.
2. Add mandatory-browser CI on its own branch and pull request.
3. Prepare a design-only Module 02 terrain plan on a separate branch and pull request.

The owner has **not** authorized merging PR #1, tagging a merge commit, selecting a licence
or implementing Module 02. Leave those decisions pending. Do not interpret a technical
recommendation to merge as a human merge instruction. Do not wait for those decisions to
perform the independent CI and planning work above.

## Read first

1. `reviews/module-01/2026-10-26-followup/FOLLOWUP_REVIEW.md`.
2. `reviews/module-01/2026-10-26-followup/VERIFICATION.json` and `README.md`.
3. `solar-site-layout/DELIVERY_REPORT.md` and `CHECKPOINT.md`.
4. `solar-site-layout/docs/CONTRACTS.md` and `README.md`.
5. `handoffs/module-01/START_HERE.md` and `ACCEPTANCE.md` for the accepted scope.
6. PR #1: https://github.com/siddhant68/solar_studio/pull/1.

The first review and its repair handoff remain historical records. Do not reopen fixed
F1–F5 or begin a new Module 01 implementation just because those older documents name
them. `START_PROMPT.md` is the original build instruction; it is not this continuation.

## Baseline and evidence

- The implementation delivery head reviewed independently is
  `82f11f035f78b3e6daf2659582690d393b53016d`.
- Its recorded source under acceptance is
  `fe15c5fda8345cbc17c2b8dc2a81fd5321fda5ef`. All seven recorded source/test/script/lock/
  fixture/probe tree identities were confirmed to match the delivery head.
- Independent macOS arm64/Python 3.12.14 run: **233 passed, no failures or skips**;
  Playwright 1.63.0 with installed Chrome, **24/24 browser subchecks**, **17 MCP steps**.
- Parallel export failures: **0/24**. Four independent processes published one initially
  unissued bundle with identical paths and byte hashes. Corrupt panel power and area
  values were rejected. Result exports stayed stable after another project reused them.
- The numerical core files were unchanged during repair. The source bindings and detailed
  results are in `VERIFICATION.json`; the original test logs, screenshots and wire
  transcript accompany it.

The earlier Linux runs and the independent Mac run are distinct evidence sets. Do not
claim that the reviewer reran Linux performance benchmarks or the REA reference pipeline,
or verified the particular final ZIP/bundle downloads supplied by your session. Those
limits are explicitly recorded in the follow-up report.

The original evidence ZIP and `FOLLOWUP_MANIFEST.json` preserve that dated review. The
portable script and any `supplemental/` files were added during Git publication and do
not belong to the original evidence manifest. Do not overwrite historical evidence.

## Git workflow

Fetch current refs first. The verification publication commit adds documents/evidence to
`claude/kind-cerf-gu33em`; it does not change application source. Check PR #1's actual
state rather than assuming a merge occurred after this document was written.

If PR #1 is still open, branch the CI and terrain-plan work separately from the latest
`origin/claude/kind-cerf-gu33em`. Open each follow-up PR with that implementation branch
as its base, and state the dependency on PR #1. This avoids presenting the entire
implementation again as a new independent change. If the owner has since merged PR #1,
branch from the updated `origin/main` instead. Do not merge either follow-up PR yourself.

Suggested branch names are `ci/module-01-browser-required` and
`docs/module-02-terrain-plan`; choose unused names if needed. Keep CI changes and terrain
planning in separate commits/PRs. Never reset or force-push another session's changes.

## Task A — status and CI

Keep independent review acceptance distinct from merge/release status. Correct stale
entry points and note that a macOS/Chrome run now exists, naming the tested environment.
Do not generalize this into Safari, Windows or Python 3.13+ support. Keep Apache-2.0 as
an undecided proposal; do not add a licence or metadata declaration on the owner's behalf.

Add a GitHub Actions workflow using maintained official actions, with versions or commit
pins verified at implementation time. The initial required job should run on Linux with
Python 3.12 and a compatible Node runtime:

1. Install the application with `uv sync --frozen` from `solar-site-layout/`.
2. Run `scripts/bootstrap_browser.sh`, using its pinned Playwright/Chromium installation.
3. Run the full test suite with `SOLAR_REQUIRE_BROWSER=1`, a dedicated
   `SOLAR_EVIDENCE_DIR`, and JUnit XML output. A missing browser must fail this job.
4. Confirm that the JUnit result has no failures, errors or skips, and that the expected
   browser/MCP evidence was actually produced. Do not hardcode 233 forever; future tests
   may increase the count, but browser and MCP execution must remain mandatory.
5. Upload test logs, JUnit XML, browser screenshots/checks and MCP evidence as downloadable
   artifacts even if a test fails. Include the tested commit and actual tool versions.

Use finite job/artifact retention settings and repository-read permissions unless a
specific step needs more. Do not add secrets, public hosting or a deploy job. A successful
local workflow-shaped command is not proof of a successful GitHub run: obtain the actual
run/check URL after the PR is pushed, or report exactly why it could not execute.

The portable reviewer supplement can be run with the application's Python:

```sh
python /absolute/repo/reviews/module-01/2026-10-26-followup/reproduce_followup.py \
  --repo /absolute/repo --out /absolute/scratch/verification
```

If application tests/scripts change while adding CI, rerun appropriate checks and retain
fresh source bindings; do not silently reuse acceptance evidence for a different tree.

## Task B — Module 02 terrain design only

Write a self-contained proposal under `handoffs/module-02-terrain/`, with a plan, draft
input/output contracts, analytic fixtures, acceptance matrix, source/reference research,
implementation milestones and unresolved owner decisions. Do not create a terrain engine
or change Module 01 computation as part of this planning task.

Research current open-source terrain tools and inspect what they actually implement.
Separate normal source analysis from REA artifact/runtime investigations. Propose REA
only where it answers a concrete shipped-behavior question, with a cloud-compatible
target and evidence plan. Do not make a missing native CAD analysis tool a dependency
of the entire module. Screen licences and implementation maturity rather than relying
on marketing descriptions.

The plan must cover:

- TIN or DEM input with explicit horizontal CRS, units, axis conventions and vertical
  datum. Evaluate a TIN-first slice with an explicit DEM adapter rather than making every
  format mandatory in the first milestone. No guessed datum transformations.
- Unknown/no-data ground: uncovered regions and holes remain unknown; no invented
  interpolation across gaps or silent extrapolation. Define partial-coverage behavior.
- Immutable source linkage: Module 01 `table_id` is only unique within its layout.
  Identify a terrain placement by source layout result ID, payload digest and table ID,
  plus the exact terrain/parameter identity. Do not treat `T_j0_i0` as globally unique.
- Rack-plane fitting: distinguish a rigid vertical lift with preserved tilt/XY from
  reorientation that changes geometry. Choose and justify the first supported operation;
  preserve the original flat-layout artifact and create a separate placement result.
- `relative_flat_datum` is not surveyed absolute elevation. Define the accepted placement
  z/reference contract and per-module elevations derived from accepted rack planes.
- Clearance checked across the entire rack footprint, not only corners. Include a hill
  that touches the middle while all corners clear, plus a void under a rack.
- Slope limits, clearance and supports as explicit inputs. Pile/support positions and
  constraints must be supplied or generated under a separately stated model; dimensions
  and module count alone do not establish pile quantity, foundation depth or structural
  approval. Distinguish above-ground support height from embedment/total pile length.
- An independent verifier with analytic planes, translated/rotated survey cases,
  unknown-ground tests, datum mismatch, a known infeasible placement and corrupted output.
- The existing shared-service/MCP architecture, result pagination, provenance, export
  identities and acceptance approach. Plan for integration through published contracts,
  not private cross-engine imports.

Give numerically specified examples a fresh agent can calculate independently. Delineate
terrain fitting from grading/cut-fill optimization, structural design and electrical
design. Keep the first terrain milestone achievable and avoid an unbounded replacement
of a complete civil-engineering suite.

## Deliver and stop

Return the CI PR/run URL, terrain-plan PR URL, exact commits and executed check results.
Name any blocked external action without disguising it as a pass. Leave one concise list
for the owner: merge/tag approval, licence choice, and Module 02 scope approval after the
proposal is available. Do not repeatedly ask those questions while independent work can
continue. No scheduled monitoring or new automation is requested.

Proceed through CI implementation and the terrain proposal; do not stop at restating this
handoff. Do not merge, tag, deploy, choose a licence or implement terrain in this task.
