# solar-site-layout: Solar Studio Module 01

This module turns a flat site outline, exclusions and module/table rules into a verified table and module layout. For that layout it reports DC nameplate capacity, area metrics, plan drawings and transferable coordinates. A browser, a CLI, an HTTP API and a stdio MCP server all call the same deterministic service. No LLM computes any number.

The output is a preliminary layout under stated assumptions: a flat site, synthetic relative heights, a user-supplied row pitch and a bounded lattice search. It is not a construction approval. Terrain, electrical design, energy yield and finance belong to later modules and are deliberately absent.

## Status

| Platform | Status |
|---|---|
| Linux x86_64 (Ubuntu 24.04, Python 3.12.3, cloud container) | **Tested.** The full test suite, real-browser checks (Chromium 153 via Playwright 1.62), real MCP client sessions, benchmarks, and a fresh-clone reproduction all ran here. |
| macOS | **Not tested.** No macOS runner was available. Every dependency ships macOS wheels and the code uses no Linux-only APIs, except the test-only `SIGKILL` fault injection and `scripts/dev_server.sh` (`setsid`). |
| Windows | **Not tested.** The test-only fault injection uses POSIX signals, and the shell helper scripts are bash. |

## Install

```sh
cd solar-site-layout
uv sync --frozen --python 3.12      # uses uv.lock; creates .venv
```

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/). Runtime dependencies: shapely (GEOS), numpy, ezdxf, jsonschema, starlette, uvicorn and mcp. The exact versions are pinned in `uv.lock` and listed in `docs/IMPLEMENTATION_NOTES.md`.

## Calculate from the CLI

```sh
S=.venv/bin/solar-layout
F=../handoffs/module-01/fixtures
$S --data-dir data validate $F/rectangle.request.json
$S --data-dir data generate $F/rectangle.request.json          # 6 tables, 24 modules, 13.2 kWp
$S --data-dir data pitch $F/pitch-3-4-5.request.json            # recommended pitch 7 m
$S --data-dir data project create $F/obstacle.request.json --name "Obstacle"
$S --data-dir data generate --project prj_…                     # 5 tables, 20 modules, 11 kWp
$S --data-dir data items res_… --kind modules --limit 100       # paged coordinates (cursor in output)
$S --data-dir data export res_… --format bundle                 # json/csv/svg/dxf/report/bundle
$S --data-dir data verify res_…                                 # re-run the independent verifier
```

Every command prints one JSON document. On success that is `{"ok": true, "result": …}` with exit status 0. On error it is `{"ok": false, "error": {"code", "message", "field", …}}` with exit status 2.

## Browser interface and HTTP API

```sh
.venv/bin/solar-layout --data-dir data serve --port 8765        # binds 127.0.0.1 only
# open http://127.0.0.1:8765/
```

The page opens with the analytic rectangle. From there you can:
- Load the other examples, or import a request `.json`.
- Edit module, table, placement and setback values; units are shown beside every field. Boundary and exclusions are edited as JSON in the coordinate editor.
- Validate, save the project (revisioned) and generate a layout.
- Inspect the totals; fit, zoom, pan and toggle layers on the plan.
- Download any export.
- Reopen a project later with `?project=prj_…`.

Results are labelled **current** or **outdated** by the input revision they came from.

The API endpoints are listed in `docs/CONTRACTS.md` §7.

## MCP access

The server is a stdio MCP server built on the official MCP Python SDK. Its tools are `validate_request`, `calculate_row_pitch`, `create_project`, `get_project`, `update_project`, `generate_layout`, `get_layout_summary`, `get_layout_items` and `export_layout`.

Generic MCP client configuration, using absolute paths:

```json
{
  "mcpServers": {
    "solar-site-layout": {
      "command": "/ABSOLUTE/PATH/solar_studio/solar-site-layout/.venv/bin/solar-layout-mcp",
      "args": ["--data-dir", "/ABSOLUTE/PATH/solar-data"]
    }
  }
}
```

For a scripted session with a wire transcript, run `.venv/bin/python scripts/mcp_session.py OUT_DIR`. It uses the SDK client and saves the JSON-RPC exchange through `scripts/mcp_wire_tap.py`.

The server needs no account, API key, network access, LLM or CAD application.

## Tests and acceptance evidence

```sh
.venv/bin/python -m pytest -q                       # full suite: core, service, exports, browser, MCP
.venv/bin/python scripts/run_acceptance.py --inspector-dir <npm dir with @modelcontextprotocol/inspector@2.12.0>
.venv/bin/python scripts/build_acceptance_report.py # writes reports/ACCEPTANCE.json (36 gates)
.venv/bin/python scripts/benchmark.py reports/BENCHMARKS.json
.venv/bin/python scripts/package_delivery.py ../dist # bundle + source zip + SHA-256 + fresh-clone reproduction
```

The browser tests need Node with the `playwright` package and a Chromium it can launch. The MCP Inspector cross-check is optional.

## Layout of this folder

| Path | Content |
|---|---|
| `src/solar_layout/` | Engine (`validation`, `geometry`, `layout`, `exact`, `verify`, `pitch`), store, service, exports, CLI, HTTP, MCP, `web/` |
| `src/solar_layout/schemas/` | JSON Schemas for `solar.layout.request/1` and `solar.row_pitch.request/1` |
| `tests/` | pytest suite; `tests/browser/ui_checks.cjs` holds the real-browser checks |
| `fixtures/` | Benchmark and stress requests (our own; the handoff fixtures stay in `../handoffs`) |
| `scripts/` | Acceptance runner, benchmarks, packaging, MCP session and wire tap, dev server |
| `references/` | Reference manifest, REA scenario definitions and probes (adapters) |
| `evidence/` | REA Evidence, reference runtime observations, acceptance runs, calculation examples, delivery verification |
| `reports/` | `REFERENCE_FINDINGS.md`, `ACCEPTANCE.json`, `BENCHMARKS.json` |
| `docs/` | `CONTRACTS.md` (schemas, conventions, policies, transports), `IMPLEMENTATION_NOTES.md` |
| `DELIVERY_REPORT.md`, `CHECKPOINT.md` | Delivery report and resume point |

## Licence

New code in this folder is released under Apache-2.0 (see `pyproject.toml`). Third-party obligations are listed in `docs/IMPLEMENTATION_NOTES.md`. No code from the reference applications is included.
