"""Stdio MCP adapter over SolarService (official MCP Python SDK, low-level server).

Each tool maps to one service operation. Success: CallToolResult with the service result
as structured content (and the same JSON as text). Domain errors: CallToolResult with
is_error=true and structured content {"error": {code, message, field?, ...}} carrying the
same domain code as HTTP and the CLI. The LLM never computes geometry: every number comes
from the deterministic service.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from . import __version__
from .errors import INTERNAL_ERROR, INVALID_INPUT, DomainError
from .service import SolarService
from .validation import load_schema

_REQUEST_SCHEMA_REF = "Layout request (solar.layout.request/1); see the schema in solar_layout/schemas"


def _tool_defs() -> list[types.Tool]:
    layout_schema = load_schema("solar.layout.request.v1.schema.json")
    pitch_schema = load_schema("solar.row_pitch.request.v1.schema.json")
    req = {k: v for k, v in layout_schema.items() if k not in ("$schema", "$id")}
    pitch = {k: v for k, v in pitch_schema.items() if k not in ("$schema", "$id")}
    rid = {"type": "string", "pattern": "^res_[0-9a-f]{24}$", "description": "Result ID returned by generate_layout"}
    pid = {"type": "string", "description": "Project ID returned by create_project"}
    ro = types.ToolAnnotations(read_only_hint=True, open_world_hint=False)
    rw = types.ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
    return [
        types.Tool(
            name="validate_request",
            description="Validate and normalize a layout request. Returns typed field errors or the normalized request, table dimensions and candidate bounds. Persists nothing.",
            input_schema={"type": "object", "properties": {"request": req}, "required": ["request"], "additionalProperties": False},
            annotations=ro,
        ),
        types.Tool(
            name="calculate_row_pitch",
            description="Limited 2D row-spacing estimate at ONE specified solar elevation (flat ground, equal heights, infinite rows, sun perpendicular to rows). Not an all-year shading guarantee or energy estimate.",
            input_schema={"type": "object", "properties": {"request": pitch}, "required": ["request"], "additionalProperties": False},
            annotations=ro,
        ),
        types.Tool(
            name="create_project",
            description="Create a project from a valid layout request. Returns the project at revision 1.",
            input_schema={"type": "object", "properties": {"request": req, "name": {"type": "string", "maxLength": 200}}, "required": ["request"], "additionalProperties": False},
            annotations=rw,
        ),
        types.Tool(
            name="get_project",
            description="Read a project: current revision, request and selected result (with whether it is current).",
            input_schema={"type": "object", "properties": {"project_id": pid}, "required": ["project_id"], "additionalProperties": False},
            annotations=ro,
        ),
        types.Tool(
            name="update_project",
            description="Replace a project's request. Compare-and-swap: fails with REVISION_CONFLICT unless expected_revision is the current revision.",
            input_schema={
                "type": "object",
                "properties": {"project_id": pid, "expected_revision": {"type": "integer", "minimum": 1}, "request": req, "name": {"type": "string", "maxLength": 200}},
                "required": ["project_id", "expected_revision", "request"],
                "additionalProperties": False,
            },
            annotations=rw,
        ),
        types.Tool(
            name="generate_layout",
            description="Generate an immutable, independently verified layout from a project revision (default: current) or an inline request. Returns result ID, digests, summary quantities and item totals; page coordinates with get_layout_items.",
            input_schema={
                "type": "object",
                "properties": {"project_id": pid, "revision": {"type": "integer", "minimum": 1}, "request": req},
                "additionalProperties": False,
            },
            annotations=rw,
        ),
        types.Tool(
            name="get_layout_summary",
            description="Read a stored result's summary, provenance, verification status and exports without loading coordinates.",
            input_schema={"type": "object", "properties": {"result_id": rid, "project_id": pid}, "required": ["result_id"], "additionalProperties": False},
            annotations=ro,
        ),
        types.Tool(
            name="get_layout_items",
            description="Page through tables or modules of a result in stable order. Default 100 items, maximum 500; never truncated silently. Continue with next_cursor.",
            input_schema={
                "type": "object",
                "properties": {
                    "result_id": rid,
                    "kind": {"enum": ["tables", "modules"]},
                    "offset": {"type": "integer", "minimum": 0},
                    "cursor": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                "required": ["result_id"],
                "additionalProperties": False,
            },
            annotations=ro,
        ),
        types.Tool(
            name="export_layout",
            description=(
                "Publish (or reuse) one export of a result inside the managed export root: json, csv, svg, dxf, report (Markdown) "
                "or bundle (zip with SHA-256 manifest) contain the immutable result only and are write-once; context is a "
                "content-addressed JSON file listing the projects and revisions that use the result. Returns the managed "
                "relative path, byte size and SHA-256."
            ),
            input_schema={
                "type": "object",
                "properties": {"result_id": rid, "format": {"enum": ["json", "csv", "svg", "dxf", "report", "bundle", "context"]}},
                "required": ["result_id", "format"],
                "additionalProperties": False,
            },
            annotations=rw,
        ),
    ]


def _dispatch(svc: SolarService, name: str, args: dict[str, Any]) -> Any:
    if name == "validate_request":
        return svc.validate_request(args.get("request"))
    if name == "calculate_row_pitch":
        return svc.calculate_row_pitch(args.get("request"))
    if name == "create_project":
        return svc.create_project(args.get("request"), name=args.get("name"))
    if name == "get_project":
        return svc.get_project(args.get("project_id"))
    if name == "update_project":
        return svc.update_project(args.get("project_id"), args.get("expected_revision"), args.get("request"), name=args.get("name"))
    if name == "generate_layout":
        return svc.generate_layout(project_id=args.get("project_id"), revision=args.get("revision"), request=args.get("request"))
    if name == "get_layout_summary":
        return svc.get_layout_summary(args.get("result_id"), project_id=args.get("project_id"))
    if name == "get_layout_items":
        return svc.get_layout_items(args.get("result_id"), args.get("kind", "modules"), offset=args.get("offset"), cursor=args.get("cursor"), limit=args.get("limit"))
    if name == "export_layout":
        return svc.export_layout(args.get("result_id"), args.get("format"))
    raise DomainError(INVALID_INPUT, f"Unknown tool {name!r}", field="name")


def _result(payload: Any, is_error: bool = False) -> types.CallToolResult:
    text = json.dumps(payload, sort_keys=True, allow_nan=False)
    return types.CallToolResult(content=[types.TextContent(text=text)], structured_content=payload, is_error=is_error)


def build_server(data_dir: str | None) -> Server:
    svc = SolarService(data_dir, interface="mcp")
    tools = _tool_defs()

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        args = params.arguments or {}
        try:
            out = await anyio.to_thread.run_sync(_dispatch, svc, params.name, args)
        except DomainError as e:
            return _result({"error": e.to_dict()}, is_error=True)
        except Exception as e:  # typed, never a bare traceback to the client
            return _result({"error": {"code": INTERNAL_ERROR, "message": f"Internal error: {type(e).__name__}: {e}"}}, is_error=True)
        if isinstance(out, list):
            out = {"items": out}
        return _result(out)

    return Server(
        "solar-site-layout",
        version=__version__,
        instructions=(
            "Solar Studio Module 01. Deterministic flat-site table layout: validate_request, calculate_row_pitch, "
            "create_project/get_project/update_project, generate_layout, get_layout_summary, get_layout_items, export_layout. "
            "All coordinates are metres in the request frame (x East, y North). Do not invent quantities; read them from results."
        ),
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def _amain(data_dir: str | None) -> None:
    server = build_server(data_dir)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="solar-layout-mcp")
    p.add_argument("--data-dir", default=os.environ.get("SOLAR_DATA_DIR"))
    args = p.parse_args(sys.argv[1:] if argv is None else argv)
    anyio.run(_amain, args.data_dir)


if __name__ == "__main__":
    main()
