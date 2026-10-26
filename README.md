# Solar Studio

An open, assistant-accessible solar design platform, beginning with a verified flat-site layout module.

**Current state (26 October 2026):** Module 01 is implemented in [`solar-site-layout/`](solar-site-layout/). The five findings from the first independent review are repaired and passed a follow-up review at `82f11f0`; all seven recorded implementation tree bindings match the tested source `fe15c5f`. The independent Mac run passed **233 tests, 24 browser checks and 17 MCP steps**. See the [follow-up review](reviews/module-01/2026-10-26-followup/FOLLOWUP_REVIEW.md) and [raw verification](reviews/module-01/2026-10-26-followup/VERIFICATION.json).

[PR #1](https://github.com/siddhant68/solar_studio/pull/1) remains open; merging/tagging and the new-code licence are owner decisions. Module 02 has not been implemented.

## Continue in Claude Cloud

Start with [CLAUDE_NEXT_HANDOFF.md](CLAUDE_NEXT_HANDOFF.md): consume the independent verification, add CI in its own PR and prepare a design-only terrain-module proposal separately. Every required report and screenshot is now accessible through Git. The original [starter prompt](START_PROMPT.md) and [Module 01 brief](handoffs/module-01/START_HERE.md) remain historical/specification context.

The first goal is: **site boundary + panel/mounting rules → panel positions, counts, DC capacity and a readable plan.** The intended application exposes the same calculation service through a browser, CLI, HTTP and MCP.

## Complete handoff

| File | Purpose |
|---|---|
| [Implementation brief](handoffs/module-01/START_HERE.md) | Context, scope, mathematics, architecture, execution milestones and deliverables |
| [REA and references](handoffs/module-01/REA_AND_REFERENCES.md) | Screened open-source targets, pinned references and the artifact investigation workflow |
| [Acceptance matrix](handoffs/module-01/ACCEPTANCE.md) | 36 mandatory gates and independently specified calculations |
| [Fixtures](handoffs/module-01/fixtures/) | Proposed request contracts, exact expected results and adversarial geometry cases |
| [Research screening](handoffs/module-01/research/SCREENING.json) | Reference observations, commits and tool package metadata |
| [Package validation](handoffs/module-01/PACKAGE_VALIDATION.json) | Documentation/fixture checks only |
| [File hashes](handoffs/module-01/SHA256SUMS.json) | Integrity of the original handoff files |

For a file-upload workflow, download the [complete ZIP](handoffs/archives/Solar_Module_01_Claude_Cloud_Brief.zip) and its [SHA-256 checksum](handoffs/archives/Solar_Module_01_Claude_Cloud_Brief.zip.sha256). The ZIP unpacks to `module-01-brief/` with the same source documents and fixtures.

## What the first module must demonstrate

- Correct table/module geometry, setbacks, holes, exclusions and supported survey coordinates.
- Honest capacity, area and limited row-spacing calculations.
- JSON/CSV coordinates, SVG/DXF plans and a calculation report.
- One usable browser workflow and real MCP client execution.
- Reproducible acceptance evidence, source archives and a Git bundle.

The supplied rectangle case must produce exactly **6 tables, 24 panels and 13.2 kWp**. Terrain, electrical diagrams and energy yield are later modules.

The brief was prepared on 25 October 2026. Reference observations, future implementation results and independently verified outputs must remain clearly distinguished.

## Review history

- [First review](reviews/module-01/2026-10-26/REVIEW.md): five reproduced findings at `f55f4be`, retained unchanged.
- [Repair delivery](solar-site-layout/DELIVERY_REPORT.md): fixes and Linux evidence bound to `fe15c5f`.
- [Independent repair verification](reviews/module-01/2026-10-26-followup/FOLLOWUP_REVIEW.md): all five accepted in the exercised cases at `82f11f0`, plus Mac tests and four-process export evidence.
- [Downloadable follow-up evidence](reviews/module-01/2026-10-26-followup/Solar_Module_01_Repair_Verification.zip).

The earlier [repair handoff](CLAUDE_REPAIR_HANDOFF.md) is superseded by [the continuation handoff](CLAUDE_NEXT_HANDOFF.md). Do not reopen completed repairs because an older document lists them.

## Module 02 proposal (for review)

[`handoffs/module-02-terrain/`](handoffs/module-02-terrain/README.md) is a design-only terrain placement proposal: plan, draft contracts, analytic fixtures with independently re-derived expectations, acceptance gates, research and the [owner decisions](handoffs/module-02-terrain/OWNER_DECISIONS.md) needed before any implementation. Nothing in it is implemented.
