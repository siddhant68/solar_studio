# Solar Studio

An open, assistant-accessible solar design platform, beginning with a verified flat-site layout module.

**Current state:** research-backed implementation handoff and analytic fixtures. The application has not been built in this repository yet. No application tests or actual REA analysis are claimed by this handoff.

## Start the build

Give an execution-enabled Claude Cloud session access to this repository and use [START_PROMPT.md](START_PROMPT.md). Begin with [the complete Module 01 brief](handoffs/module-01/START_HERE.md).

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
