# Independent review — Solar Studio Module 01

26 October 2026. Reviewed branch `claude/kind-cerf-gu33em`, commit `f55f4be5bb34951a9722bc6024f7242142ec22c3`. **Recommendation: request changes before merging or starting Module 02.** The implementation is a useful foundation, but five reproducible findings need attention.

## What was independently verified

- The remote branch has the seven reported commits and points at `f55f4be`; `main` is still the original handoff commit `9308eef`. There was no pull request at the time of this review.
- All seven recorded source/test/script/lock/fixture/probe tree identities in the acceptance metadata match the reviewed HEAD. The later delivery commits have not silently changed the tested implementation trees.
- Installed using `uv sync --frozen` into an isolated review environment on macOS arm64, Python 3.12.14. The supplied pytest suite completed in 17.506 s: **206 passed, 1 skipped, 0 failed**. The skip is the browser test, whose default Node/Playwright setup was absent. The real MCP client test is included in the passing set.
- Ran the supplied browser checks separately with Playwright 1.62.0 and installed Chrome 156.0.8078.47: **13/14 subchecks passed**. The no-browser-errors subcheck failed on one 404 console error. This is separate from the correctness failures below. The missing `/favicon.ico` endpoint is a plausible source; the offending request URL should be logged before deciding the fix.
- Ran additional real-browser delayed-autosave and delayed-SVG experiments, natural parallel service exports, an explicitly scheduled export overlap, export-context changes and deliberate verifier corruption tests. Their observations are retained alongside this report.
- Inspected generated browser drawings at overview and the captured race screenshots. The normal projected/rotated plan is readable and includes the required site, exclusions, modules, scale and quantities.

The original Linux run's 207 passing tests remain its own evidence, not a claim that this Mac repeated all of that run identically. I did not rerun the upstream reference build or REA investigation. The committed records show selected-asset static analysis plus runtime observations, and explicitly retain the main-bundle static-analysis limitation. The minimum reference-artifact work is substantive; it should continue to be described with that scope.

## Findings, ordered by priority

### F1 — [P1] Capture the submitted inputs before awaiting autosave

Source: [web/app.js:180](https://github.com/siddhant68/solar_studio/blob/f55f4be5bb34951a9722bc6024f7242142ec22c3/solar-site-layout/src/solar_layout/web/app.js#L180), with the current-status comparison at [line 104](https://github.com/siddhant68/solar_studio/blob/f55f4be5bb34951a9722bc6024f7242142ec22c3/solar-site-layout/src/solar_layout/web/app.js#L104).

`generate()` awaits `save()` and then captures the live editor JSON. If the user changes inputs during that save, the captured JSON belongs to the new edits while the persisted revision used for calculation still contains the old inputs. `resultIsCurrent()` compares against that misbound snapshot and can return true.

Real-browser reproduction: start from the rectangle, press Generate, hold the project-create response after the server saves width 1 m, edit module width to 2 m, then release the response. The editor is dirty, but the old **24-panel, table-width-2 m** result is labelled **current**. Width 2 m requires a different **16-panel, table-width-4 m** result. The captured state even says the result snapshot width is 2 while its saved input width is 1.

Repair: bind one immutable submitted request, project identity and revision across save/generate. Changes during either await must remain dirty and make the older result historical, or cause a fresh explicit save/generate of the changed input. Never snapshot the live editor after the save and associate it with a different persisted request. Test both project create and update delays.

Evidence: `browser-races.json` → `edit_during_autosave`, `race-autosave.png`.

### F2 — [P1] Reject stale SVG responses before changing any displayed result

Source: [web/app.js:213](https://github.com/siddhant68/solar_studio/blob/f55f4be5bb34951a9722bc6024f7242142ec22c3/solar-site-layout/src/solar_layout/web/app.js#L213).

The response-order check protects the layout POST, but `display()` then awaits the SVG fetch with no freshness guard afterward. An older drawing request can finish last and overwrite the plan, quantities and download URL while `state.displayed` and the current banner refer to the newer result.

Real-browser reproduction: hold revision 1's SVG; change width to 2 m and generate revision 2; let revision 2 render its **16 panels**; release revision 1's SVG. The page now draws **24 panels**, the summary identifies revision 1, the banner still reads **Current result for revision 2**, and Download points to revision 1. This is a wrong-artifact problem, not just a label issue.

Repair: use a generation/display token across all awaits and commit the SVG, summary, status and export link as one coherent view only if the token is still current. Invalidate outstanding renders when opening a different project or importing/loading another input. Cancellation can reduce wasted work but does not replace a final freshness check.

Evidence: `browser-races.json` → `delayed_svg_*`, `race-delayed-svg.png`.

### F3 — [P2] Export temporary filenames collide between HTTP worker threads

Source: [exports/__init__.py:71](https://github.com/siddhant68/solar_studio/blob/f55f4be5bb34951a9722bc6024f7242142ec22c3/solar-site-layout/src/solar_layout/exports/__init__.py#L71).

The temporary name contains only the destination and process ID. Concurrent exports of the same result/format in one process open the same `.partial` file. One rename removes the pathname the other thread expects. Natural parallel service calls reproduced **20 failures in 24 calls**, and a controlled overlap deterministically produced a `FileNotFoundError`. HTTP executes these operations in worker threads, so simultaneous requests can hit this path.

Repair: use a unique, exclusively created staging file for each call and coordinate publication/metadata consistently for a result/format. Exercise same-format requests and bundle/subformat overlap through HTTP as well as direct service calls. Account for the process-global ezdxf metadata option if DXF writes can overlap. Returned hashes must describe the file actually published and downloaded.

Evidence: `adversarial-results.json` → `natural_parallel_exports`, `controlled_parallel_exports`; `adversarial_probes.py`.

### F4 — [P2] The same immutable result's export changes when another project uses it

Source: [exports/__init__.py:110](https://github.com/siddhant68/solar_studio/blob/f55f4be5bb34951a9722bc6024f7242142ec22c3/solar-site-layout/src/solar_layout/exports/__init__.py#L110), [exports/jsonx.py:32](https://github.com/siddhant68/solar_studio/blob/f55f4be5bb34951a9722bc6024f7242142ec22c3/solar-site-layout/src/solar_layout/exports/jsonx.py#L32).

An export reads the mutable `result_sources` associations and writes them into the result file. Generate an inline result, export JSON, create another project with the same numerical inputs and generate, then export JSON again: the result ID and numerical payload are identical, but the JSON bytes/hash change at the **same path** because `project_sources` has grown. Existing export references and a previously issued manifest can therefore lose their old byte identity after a normal workflow.

Repair: define the export provenance snapshot explicitly. Either keep result-only exports stable and put project associations in a separate contextual export, or include a context/snapshot identity in versioned artifact paths and preserve previously issued files. Build bundles from one fixed snapshot, not independently refreshed mutable files. Add an associate-another-project/revision/restart regression. Merely documenting that exports are deterministic is insufficient while the current context silently changes their bytes.

Evidence: `additional-results.json` → `export_context_change`; initial before/after hashes also occur in `adversarial-results.json`.

### F5 — [P2] The verifier accepts corrupted power and area records

Source: [verify.py:175](https://github.com/siddhant68/solar_studio/blob/f55f4be5bb34951a9722bc6024f7242142ec22c3/solar-site-layout/src/solar_layout/verify.py#L175) and [line 200](https://github.com/siddhant68/solar_studio/blob/f55f4be5bb34951a9722bc6024f7242142ec22c3/solar-site-layout/src/solar_layout/verify.py#L200).

The capacity check multiplies record count by the request's power; it never checks each module record's `power_wp`. Changing one record from 550 W to **123456 W** still returns `ok=true`: the exported records sum to **136.106 kWp** while the verified summary reports **13.2 kWp**. Likewise, changing gross and buildable area to 999999 m² and adjusting the coverage ratios consistently still passes, because the verifier trusts the area denominators.

Repair: validate record power and other contract-critical fields against the input, reconcile record sums with the summary, and independently validate area values/bounds against original geometry (or explicitly narrow any verification claim). Check payload integrity as appropriate; a hash check complements, rather than replaces, independent calculation checks. Add the deliberately inconsistent records and consistently corrupted summary to the corruption test suite.

Evidence: `additional-results.json` → `corrupt_module_power`; `adversarial-results.json` → `corrupt_area_verifier`.

## Administrative follow-up

- Update `CHECKPOINT.md` and the delivery report: pushing is no longer blocked. It is fine to include that correction with the repair/evidence commit.
- Decide the new-code licence consistently: README says released under Apache-2.0 while the delivery report calls that a proposal. Add the actual selected licence text when settled.
- Document/bootstrap browser prerequisites with pinned tooling so a fresh runner cannot skip UI coverage unnoticed.
- Regenerate acceptance evidence on repaired final source. V02 and the broad corruption-verification claim cannot be accepted on the current adversarial results. Do not carry forward 36/36 solely because the original tests still pass.
- Open a PR for review after the repairs. Keep `main` unchanged until reviewed. No PR, GitHub comment, remote commit or application source change was made by this review.

## Verification scope and artifacts

`pytest-junit.xml` / `pytest.log`: supplied tests on this Mac. `supplied-browser-checks/`: supplied browser tests on Chrome. `browser_races.cjs`: additional real-browser reproductions. `adversarial_probes.py`: service/export/verifier probes. `additional-results.json`: record-power corruption, mutable export context and exact source-tree binding.

The final downloaded ZIP and Git bundle mentioned in the agent message were not supplied to this review, so byte-for-byte equality of those particular downloads with `f55f4be` was not independently established. The remote branch and implementation/evidence tree bindings were verified directly.
