"""Real MCP client session for Module 02 terrain placement (gate TS05).

Uses the official MCP Python SDK client over stdio. The server is started through
mcp_wire_tap.py, so the complete JSON-RPC exchange is kept byte-for-byte as JSONL.

    python scripts/terrain_mcp_session.py OUT_DIR [DATA_DIR]

Steps: generate the T03 layout, validate and import the hill-fan terrain, place (L = 11.1 m
on the interior hill), page tables/modules/supports with cursors, export json/csv/supports_csv,
re-verify, and request a placement with a different expected vertical reference (typed
DATUM_MISMATCH). Writes OUT_DIR/terrain-mcp-wire-transcript.jsonl and
OUT_DIR/terrain-mcp-session-steps.json. Exit status 0 only if every step behaved as specified.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT.parent / "handoffs" / "module-02-terrain" / "fixtures"


def load(rel: str) -> dict:
    return json.loads((FIXTURES / rel).read_text())


async def run(out: Path, data_dir: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    wire = out / "terrain-mcp-wire-transcript.jsonl"
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

    case = load("cases/T03.json")
    async with stdio_client(params) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as s:
            init = await s.initialize()
            step("initialize", init.server_info.name == "solar-site-layout", protocol=init.protocol_version, server=init.server_info.name)
            names = [t.name for t in (await s.list_tools()).tools]
            terrain_tools = ["validate_terrain", "import_terrain", "get_terrain", "place_on_terrain", "get_placement_summary", "get_placement_items", "export_placement", "verify_stored_placement"]
            step("tools/list includes the terrain tools", all(t in names for t in terrain_tools), tools=names)

            async def call(name: str, args: dict):
                r = await s.call_tool(name, args)
                return r.is_error, r.structured_content

            err, gen = await call("generate_layout", {"request": load(case["layout"]["request"])})
            step("generate_layout (T03 layout)", not err and gen["result_id"] == case["layout"]["observed_result_id"] and gen["payload_digest"] == case["layout"]["observed_payload_digest"], result_id=gen.get("result_id"))

            surface = load("surfaces/hill-fan.surface.json")
            err, val = await call("validate_terrain", {"surface": surface})
            step("validate_terrain", not err and val["valid"] and val["terrain_id"] == case["placement_request"]["terrain"], terrain_id=val.get("terrain_id"))
            err, ter = await call("import_terrain", {"surface": surface})
            step("import_terrain", not err and ter["terrain_id"] == case["placement_request"]["terrain"] and ter["reused_existing_terrain"] is False, terrain_id=ter.get("terrain_id"), info=ter.get("info"))
            err, got = await call("get_terrain", {"terrain_id": ter["terrain_id"]})
            step("get_terrain", not err and got["terrain_digest"] == ter["terrain_digest"] and got["vertical"]["id"] == "local:fixture-datum")

            err, pl = await call("place_on_terrain", {"request": case["placement_request"]})
            pid = pl.get("placement_id") if not err else None
            step("place_on_terrain (T03 interior hill)", not err and pl["verification"]["ok"] and pl["summary"]["counts"]["placed_tables"] == 1, placement_id=pid, counts=pl.get("summary", {}).get("counts"))
            err, again = await call("place_on_terrain", {"request": case["placement_request"]})
            step("place_on_terrain repeat reuses the stored placement", not err and again["placement_id"] == pid and again["reused_existing_placement"] is True)

            err, summ = await call("get_placement_summary", {"placement_id": pid})
            step("get_placement_summary", not err and summ["payload_digest"] == pl["payload_digest"] and summ["items"]["modules"]["total"] == 4 and summ["items"]["supports"]["total"] == 3)

            err, tabs = await call("get_placement_items", {"placement_id": pid, "kind": "tables"})
            t = tabs["items"][0] if not err else {}
            step(
                "get_placement_items tables: L = 11.1 m, min clearance 0.5 m at (4, 4)",
                not err and abs(t["lower_edge_z_m"] - 11.1) <= 1e-9 and abs(t["min_clearance_m"] - 0.5) <= 1e-9 and t["min_clearance_at_xy_m"] == [4.0, 4.0],
                lower_edge_z_m=t.get("lower_edge_z_m"),
                min_clearance_m=t.get("min_clearance_m"),
                min_clearance_at_xy_m=t.get("min_clearance_at_xy_m"),
            )
            seen, pages = [], 0
            err, page = await call("get_placement_items", {"placement_id": pid, "kind": "modules", "limit": 3})
            while True:
                pages += 1
                seen += [m["module_id"] for m in page["items"]]
                if not page["next_cursor"]:
                    break
                err, page = await call("get_placement_items", {"placement_id": pid, "kind": "modules", "cursor": page["next_cursor"], "limit": 3})
            step("get_placement_items pages all modules once by cursor", not err and len(seen) == 4 and len(set(seen)) == 4 and pages == 2, pages=pages)
            err, sups = await call("get_placement_items", {"placement_id": pid, "kind": "supports"})
            heights = [round(x["above_ground_m"], 12) for x in sups["items"]] if not err else []
            step("get_placement_items supports: 0.725, 0.5, 0.725 m above ground", not err and heights == [0.725, 0.5, 0.725], above_ground_m=heights)
            err, badc = await call("get_placement_items", {"placement_id": pid, "kind": "supports", "cursor": "garbage"})
            step("get_placement_items invalid cursor -> INVALID_CURSOR", err and badc["error"]["code"] == "INVALID_CURSOR")

            for fmt in ("json", "csv", "supports_csv"):
                err, ex = await call("export_placement", {"placement_id": pid, "format": fmt})
                step(f"export_placement {fmt}", not err and len(ex["sha256"]) == 64 and ex["path"].startswith(pid + "/v1/"), path=ex.get("path"), sha256=ex.get("sha256"), bytes=ex.get("bytes"))

            err, ver = await call("verify_stored_placement", {"placement_id": pid})
            step("verify_stored_placement", not err and ver["ok"], checks={k: v["ok"] for k, v in ver.get("checks", {}).items()})

            wrong = copy.deepcopy(case["placement_request"])
            wrong["expected_vertical"] = {"kind": "local", "id": "local:other-benchmark"}
            err, dm = await call("place_on_terrain", {"request": wrong})
            step("place_on_terrain with another vertical reference -> DATUM_MISMATCH", err and dm["error"]["code"] == "DATUM_MISMATCH", error=dm.get("error") if err else None)

            err, nf = await call("get_placement_summary", {"placement_id": "plc_000000000000000000000000"})
            step("unknown placement -> PLACEMENT_NOT_FOUND", err and nf["error"]["code"] == "PLACEMENT_NOT_FOUND")

    lines = wire.read_text().splitlines()
    msgs = [json.loads(line) for line in lines]
    methods = [m["message"].get("method") for m in msgs if m["dir"] == "client->server"]
    calls = [m["message"]["params"]["name"] for m in msgs if m["dir"] == "client->server" and m["message"].get("method") == "tools/call"]
    step(
        "wire transcript retained",
        "initialize" in methods and "tools/list" in methods and {"import_terrain", "place_on_terrain", "get_placement_items", "export_placement"} <= set(calls),
        wire_lines=len(lines),
        tool_calls=len(calls),
    )
    (out / "terrain-mcp-session-steps.json").write_text(
        json.dumps({"client": "mcp Python SDK ClientSession over stdio_client", "server_command": params.args[3:], "data_dir": str(data_dir), "steps": steps}, indent=1)
    )
    return 0 if all(st["ok"] for st in steps) else 1


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    data_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else out / "data"
    sys.exit(anyio.run(run, out, data_dir))


if __name__ == "__main__":
    main()
