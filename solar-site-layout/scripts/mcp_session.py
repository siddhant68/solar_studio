"""Real MCP client session against the stdio server (S02 evidence).

Uses the official MCP Python SDK client (stdio transport). The server is started through
mcp_wire_tap.py so the complete JSON-RPC exchange is retained byte-for-byte as JSONL.

    python scripts/mcp_session.py OUT_DIR [DATA_DIR]

Writes OUT_DIR/mcp-wire-transcript.jsonl, OUT_DIR/mcp-session-steps.json and exports.
Exit status 0 only if every expected step behaved as specified.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT.parent / "handoffs" / "module-01" / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


async def run(out: Path, data_dir: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    wire = out / "mcp-wire-transcript.jsonl"
    if wire.exists():
        wire.unlink()
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "scripts" / "mcp_wire_tap.py"), str(wire), "--", sys.executable, "-m", "solar_layout.mcp_server", "--data-dir", str(data_dir)],
        cwd=str(ROOT),
    )
    steps: list[dict] = []

    def step(name: str, ok: bool, **info) -> None:
        steps.append({"step": name, "ok": bool(ok), **info})
        print(("PASS " if ok else "FAIL ") + name)

    async with stdio_client(params) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as s:
            init = await s.initialize()
            step("initialize", init.server_info.name == "solar-site-layout", protocol=init.protocol_version, server=init.server_info.name, version=init.server_info.version)
            tools = await s.list_tools()
            names = [t.name for t in tools.tools]
            expected = ["validate_request", "calculate_row_pitch", "create_project", "get_project", "update_project", "generate_layout", "get_layout_summary", "get_layout_items", "export_layout"]
            step("tools/list", names == expected, tools=names)

            async def call(name: str, args: dict):
                r = await s.call_tool(name, args)
                return r.is_error, r.structured_content

            err, pitch = await call("calculate_row_pitch", {"request": fixture("pitch-3-4-5.request.json")})
            step("calculate_row_pitch 3-4-5", not err and abs(pitch["recommended_pitch_m"] - 7.0) < 1e-9 and abs(pitch["shadow_clear_gap_m"] - 3.0) < 1e-9, recommended_pitch_m=pitch.get("recommended_pitch_m"))

            bad = fixture("rectangle.request.json")
            bad["frame"]["units"] = "deg"
            err, v = await call("validate_request", {"request": bad})
            step("validate_request rejects degree units", not err and v["valid"] is False and v["error"]["code"] == "UNSUPPORTED_FRAME", code=v.get("error", {}).get("code"))

            err, proj = await call("create_project", {"request": fixture("obstacle.request.json"), "name": "MCP obstacle"})
            pid = proj["project_id"]
            step("create_project", not err and proj["revision"] == 1, project_id=pid)

            edited = fixture("obstacle.request.json")
            edited["table"]["tilt_deg"] = 10.0
            err, upd = await call("update_project", {"project_id": pid, "expected_revision": 1, "request": edited})
            step("update_project (CAS rev 1 -> 2)", not err and upd["revision"] == 2)
            err, conflict = await call("update_project", {"project_id": pid, "expected_revision": 1, "request": edited})
            step("update_project stale revision -> REVISION_CONFLICT", err and conflict["error"]["code"] == "REVISION_CONFLICT", code=conflict["error"]["code"] if err else None)

            err, gen = await call("generate_layout", {"project_id": pid})
            rid = gen["result_id"]
            q = gen["summary"]["quantities"]
            step("generate_layout", not err and q["module_count"] == 20 and q["table_count"] == 5 and abs(q["dc_capacity_kwp"] - 11.0) < 1e-9 and gen["selection"] == "selected" and gen["verification"]["ok"], result_id=rid, modules=q["module_count"], kwp=q["dc_capacity_kwp"])

            err, summ = await call("get_layout_summary", {"result_id": rid, "project_id": pid})
            step("get_layout_summary", not err and summ["payload_digest"] == gen["payload_digest"] and summ["project_status"]["is_current"], payload_digest=summ["payload_digest"])

            seen = []
            err, page = await call("get_layout_items", {"result_id": rid, "kind": "modules", "limit": 8})
            seen += [m["module_id"] for m in page["items"]]
            pages = 1
            while page["next_cursor"]:
                err, page = await call("get_layout_items", {"result_id": rid, "kind": "modules", "cursor": page["next_cursor"], "limit": 8})
                seen += [m["module_id"] for m in page["items"]]
                pages += 1
            step("get_layout_items pages through all modules once", not err and len(seen) == 20 and len(set(seen)) == 20 and pages == 3, pages=pages)
            err, badc = await call("get_layout_items", {"result_id": rid, "cursor": "garbage"})
            step("get_layout_items invalid cursor -> INVALID_CURSOR", err and badc["error"]["code"] == "INVALID_CURSOR")

            exports = {}
            for fmt in ("svg", "csv", "report", "bundle"):
                err, ex = await call("export_layout", {"result_id": rid, "format": fmt})
                exports[fmt] = ex
                step(f"export_layout {fmt}", not err and len(ex["sha256"]) == 64 and ex["path"].startswith(rid + "/"), path=ex.get("path"), sha256=ex.get("sha256"), bytes=ex.get("bytes"))
            err, trav = await call("export_layout", {"result_id": "../../etc/passwd", "format": "json"})
            step("export_layout traversal attempt is typed", err and trav["error"]["code"] == "RESULT_NOT_FOUND")

    lines = wire.read_text().splitlines()
    msgs = [json.loads(line) for line in lines]
    methods = [m["message"].get("method") for m in msgs if m["dir"] == "client->server"]
    step("wire transcript retained", "initialize" in methods and "tools/list" in methods and methods.count("tools/call") >= 15, wire_lines=len(lines))
    (out / "mcp-session-steps.json").write_text(json.dumps({"client": "mcp Python SDK ClientSession over stdio_client", "server_command": params.args[3:], "data_dir": str(data_dir), "steps": steps}, indent=1))
    return 0 if all(s["ok"] for s in steps) else 1


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    data_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else out / "data"
    sys.exit(anyio.run(run, out, data_dir))


if __name__ == "__main__":
    main()
