# Independent verification after the Module 01 repairs

Start with [FOLLOWUP_REVIEW.md](FOLLOWUP_REVIEW.md). The five findings from the first
review were accepted as resolved in the exercised cases at implementation head
`82f11f035f78b3e6daf2659582690d393b53016d`.

The independent Mac run passed 233 tests without failures or skips, 24 browser subchecks
and 17 real MCP steps. Additional observations include four independent processes
publishing one bundle with the same byte hash. This complements the agent's Linux run;
it does not establish Windows, Safari or unrestricted platform support.

- [VERIFICATION.json](VERIFICATION.json): source binding and additional checks.
- [pytest-junit.xml](pytest-junit.xml) / [pytest.log](pytest.log): complete local test result.
- [Browser evidence](suite/browser/ui-checks.json) and screenshots in that folder.
- [MCP steps](suite/mcp/mcp-session-steps.json) / [wire transcript](suite/mcp/mcp-wire-transcript.jsonl).
- [Repeated original failure probes](adversarial-results.json).
- [Original evidence hashes](FOLLOWUP_MANIFEST.json).
- [Downloadable evidence ZIP](Solar_Module_01_Repair_Verification.zip) and its checksum.

`FOLLOWUP_MANIFEST.json` and the ZIP preserve the original review artifact. The README,
portable script and any `supplemental/` observations were added when publishing the
review into Git. They are intentionally separate from that original hash inventory.

## Repeat the extra checks in cloud

Use the application's Python environment and absolute paths:

```sh
python /absolute/repo/reviews/module-01/2026-10-26-followup/reproduce_followup.py \
  --repo /absolute/repo \
  --out /absolute/scratch/followup
```

This runs the corrupt-power and four-process publication checks and verifies the recorded
source-tree binding. It does not alter the original evidence, run the whole acceptance
suite, merge a PR, or publish a GitHub approval.

Absolute Mac paths inside the original observations are provenance only. Cloud sessions
can read every referenced source/report here through Git without access to that Mac.
