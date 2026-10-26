# Repair request for the Claude session

Continue on `claude/kind-cerf-gu33em` in `siddhant68/solar_studio`. An independent review reproduced five findings at `f55f4be`. Read the attached `REVIEW.md`, JSON observations and browser screenshots; preserve the existing numerical core and reference evidence.

1. Bind generation to the exact input snapshot actually saved. Test edits while project creation and project update responses are delayed. An old 24-module result must never be current for the edited 16-module input.
2. Guard the SVG/render stage as well as the layout POST. Hold an older SVG until a newer result is fully shown, then release it. Plan geometry, quantities, status, identity and download must all remain the newer result. Also cover switching projects/importing inputs while requests are outstanding.
3. Fix concurrent exports with unique staging paths and coherent publication. Test at least 24 simultaneous same-format HTTP requests, bundle/subformat overlap and returned/file/bundle hashes. Avoid process-global DXF option races.
4. Make export context explicit and stable/versioned. Reusing the same numerical result from another project must not silently overwrite a previously issued artifact at the same identity. Snapshot bundle inputs once.
5. Extend the independent verifier to catch corrupt per-module power, inconsistent record capacity, and consistently falsified area/coverage denominators. Retain independent geometry checks; do not solve this solely by calling the generator again.

Add regression tests for the real interleavings, fix the reported browser 404 with its request URL identified, and rerun the full tests, real browser suite, MCP session and relevant benchmarks against final source. Update the acceptance matrix honestly; do not retain 36/36 on obsolete evidence.

Update the checkpoint and delivery report to say the push succeeded, reconcile the licence wording, commit/push the fixes and produce a PR for review. Deliver new hashes/source bundle and a concise finding-by-finding response. Do not start Module 02 yet.

Reproducer portability: set `SOLAR_REVIEW_REPO` to the repository root and `SOLAR_REVIEW_OUT` to a writable evidence folder before running `adversarial_probes.py` in the installed Python environment. For `browser_races.cjs`, set `SOLAR_REVIEW_PLAYWRIGHT` to an installed Playwright module directory, `SOLAR_REVIEW_BASE` to the local server URL and `SOLAR_REVIEW_CHANNEL=chromium` on a Linux runner with Playwright Chromium installed. The script is a bug reproducer, so success means observations were captured; it is not a passing acceptance test.
