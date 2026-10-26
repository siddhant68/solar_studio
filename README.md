# Solar Studio

An open, assistant-accessible solar design platform, beginning with a verified flat-site layout module.

**Build status (25 October 2026):** Module 01 is implemented in [`solar-site-layout/`](solar-site-layout/). See its [delivery report](solar-site-layout/DELIVERY_REPORT.md), [acceptance gates](solar-site-layout/reports/ACCEPTANCE.json) (36/36 recorded pass, bound to source commit `f16944e`) and [README](solar-site-layout/README.md). The handoff text below is unchanged.

**Current state:** Module 01 is implemented on `claude/kind-cerf-gu33em`. An independent review reproduced five findings; repair and revalidate them before merging. The original brief and fixtures remain the specification.

## Continue in Claude Cloud

Give an execution-enabled Claude Cloud session access to this branch and follow [CLAUDE_REPAIR_HANDOFF.md](CLAUDE_REPAIR_HANDOFF.md). It points to the review evidence, required repairs and final verification. The [original starter prompt](START_PROMPT.md) and [complete Module 01 brief](handoffs/module-01/START_HERE.md) are retained for context.

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

## Current review and repair handoff

Module 01 has an implementation on `claude/kind-cerf-gu33em` and an independent review with five reproducible findings. **Repair and revalidate before merging.** Start the next Claude Cloud session with [CLAUDE_REPAIR_HANDOFF.md](CLAUDE_REPAIR_HANDOFF.md). The [full review and evidence](reviews/module-01/2026-10-26/REVIEW.md) and [downloadable review ZIP](reviews/module-01/2026-10-26/Solar_Module_01_Independent_Review.zip) are included. The original Module 01 handoff above remains the specification.
