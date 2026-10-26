# Review repair evidence (independent review of 26 October 2026)

The review itself lives in `../../../reviews/module-01/2026-10-26/` and is not modified. This folder records what the reviewer's reproducers and the new regression checks showed **before** the repair (source identical to `f55f4be`, checked out at `b7a3beb`) and **after** it.

## before/ (unrepaired source)

| File | What it shows |
|---|---|
| `adversarial-results.json` | Reviewer's `adversarial_probes.py`, run unchanged in this container: natural parallel CSV exports fail (`FileNotFoundError`); the controlled overlap fails; JSON bytes change at the same path after a second project reuses the result (`project_sources` grows); consistently falsified areas pass the verifier. The tiny-keepout probe is correct behaviour (no tables, verified) and is not a finding. |
| `browser-races.json`, `race-autosave.png`, `race-delayed-svg.png` | Reviewer's `browser_races.cjs` with `SOLAR_REVIEW_CHANNEL=chromium`: F1, a 24-module result labelled **current** although the saved input has width 1 m and the editor 2 m; F2, after the held SVG is released the page shows 24 modules and a revision-1 identity and download link under a "Current result for revision 2" banner. |
| `find404.cjs` | Script that located the browser 404: `GET /favicon.ico` (only full Chromium, `channel: "chromium"`, requests it; the headless shell used by the original checks does not). |
| `pytest-review-regressions-before.log` | `tests/test_review_regressions.py` against the unrepaired source: 21 failures, including the real `FileNotFoundError` collisions, the changing JSON, a rebuilt (new inode) export, and every F5 corruption passing. A few failures there are missing new APIs (`_write_staged`, the `context` format) rather than the defect itself. |
| `ui-checks-new-suite-on-b7a3beb.json` | The extended `tests/browser/ui_checks.cjs` against the unrepaired client: the favicon 404 (logged with its URL), F1 create-delay, F1 update-delay, F2 stale SVG, project switch and import while pending all fail. |

## after/ (repaired source)

| File | What it shows |
|---|---|
| `adversarial_probes_after.py`, `adversarial-results.json` | Copy of the reviewer's probe adapted to the renamed staging writer (`_write_staged`), with the controlled overlap calling `_build_unlocked` because the service now serializes the writers. 0 of 24 natural exports fail; both overlapping writers succeed with the same SHA-256; the JSON export has the same path and bytes after another project reuses the result (no `project_sources`); the falsified areas fail the verifier. |
| `browser_races_after.cjs`, `browser-races.json`, `race-*.png` | Copy of the reviewer's browser script that waits for the "not displayed" notice instead of the buggy 24-module state, which no longer occurs. F1: the result is **outdated**, its snapshot and the saved input both have width 1 m, the edit stays dirty. F2: after the old SVG is released, the page still shows the 16-module revision-2 result, identity, banner and download link. |

The acceptance run (`../acceptance/`) re-executes all of these checks as tests on the final source commit; see `../../reports/ACCEPTANCE.json`.
