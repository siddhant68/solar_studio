# Evidence index

| Folder | Authority | Content |
|---|---|---|
| `rea/doctor.json` | REA | `rea doctor` on this container: node 24.22.1 healthy; the native providers (Hopper, Ghidra, IDA, JADX) are absent, which JavaScript analysis does not need. |
| `rea/static/` | **REA-static** | `analyze-javascript-application` runs on the built reference `dist/`. Attempt 4 completed (exit 0); its full Evidence bundle is `attempt4-html-worker-chunks.evidence-bundle.json.gz` and the REA summary view is `….summary.json`. Attempts 1–3 timed out, and their error envelopes are kept here. Their large partial graphs are in the separate evidence archive (see the `_retained_note` SHA-256 fields). Each attempt also has `*.stderr.jsonl` (REA progress) and `*.exit`. |
| `rea/runtime-scenarios/` | **REA-runtime** | `capture-browser-scenario` Evidence for R03 S1/S2/S3 (`*.evidence.json.gz`), defined by `../references/scenarios/*.rea-scenario.json`. `*/summary.json` is extracted by `../references/probes/extract_rea_scenario.py`. Screenshot PNGs were extracted and verified against REA's SHA-256 (only the key steps for S2). |
| `rea/execution/` | **REA-runtime** | `observe-web-execution` precise-coverage Evidence: an idle window and a window covering the pitch/tilt change (`*.json.gz`), produced by `../references/probes/agv_rea_execution_probe.cjs`. `coverage-*.json` are produced from that Evidence by `../references/probes/rea_coverage_locate.py`. `first-attempt-*.json` records the first probe, which acted before REA armed. |
| `runtime/agv/` | **PW-runtime**, not REA | Playwright companion scenarios on the same built reference: live input values, readouts, stored design JSON, screenshots. |
| `acceptance/` | Our acceptance run | JUnit XML, test-case outcomes, browser checks with screenshots (`browser/`), MCP SDK session and wire transcript (`mcp/`), second MCP client cross-check with MCP Inspector CLI 2.12.0 (`mcp-inspector/`), S06 memory measurement, and run metadata bound to the source commit. |
| `examples/` | Calculation examples | CLI-generated results and every export for each analytic fixture, plus the 3-4-5 pitch result and an error example. |
| `delivery/` | Packaging | Git bundle and source ZIP verification, and the fresh-clone reproduction log. |

REA output is data. Nothing extracted from it was executed.
