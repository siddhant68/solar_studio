"""Command-line adapter over SolarService.

Every command prints one JSON document to stdout:
  success: {"ok": true, "result": ...}                     exit status 0
  domain error: {"ok": false, "error": {code, message, ...}}  exit status 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .errors import INTERNAL_ERROR, DomainError
from .jsonio import loads_strict


def _read_json(path: str) -> Any:
    data = sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()
    return loads_strict(data)


def _emit(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, indent=1, sort_keys=True, allow_nan=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="solar-layout", description="Solar Studio Module 01: site to layout")
    p.add_argument("--data-dir", default=None, help="state directory (default: $SOLAR_DATA_DIR or ./data)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("validate", help="validate and normalize a layout request")
    s.add_argument("request")
    s = sub.add_parser("pitch", help="2D row-spacing estimate at a specified solar elevation")
    s.add_argument("request")
    proj = sub.add_parser("project", help="project operations")
    psub = proj.add_subparsers(dest="pcmd", required=True)
    s = psub.add_parser("create")
    s.add_argument("request")
    s.add_argument("--name")
    s = psub.add_parser("get")
    s.add_argument("project_id")
    s = psub.add_parser("update")
    s.add_argument("project_id")
    s.add_argument("request")
    s.add_argument("--expected-revision", type=int, required=True)
    s.add_argument("--name")
    psub.add_parser("list")
    s = sub.add_parser("generate", help="generate an immutable layout result")
    s.add_argument("request", nargs="?", help="inline request file (omit with --project)")
    s.add_argument("--project")
    s.add_argument("--revision", type=int)
    s = sub.add_parser("summary")
    s.add_argument("result_id")
    s.add_argument("--project")
    s = sub.add_parser("items")
    s.add_argument("result_id")
    s.add_argument("--kind", default="modules", choices=["tables", "modules"])
    s.add_argument("--offset", type=int)
    s.add_argument("--cursor")
    s.add_argument("--limit", type=int)
    s = sub.add_parser("export")
    s.add_argument("result_id")
    s.add_argument("--format", required=True)
    s = sub.add_parser("verify", help="re-run the independent verifier on a stored result")
    s.add_argument("result_id")
    s = sub.add_parser("serve", help="run the local HTTP API and browser interface")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    sub.add_parser("mcp", help="run the stdio MCP server")
    return p


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "serve":
        from .http_app import serve

        serve(args.host, args.port, args.data_dir)
        return 0
    if args.cmd == "mcp":
        from .mcp_server import main as mcp_main

        mcp_main(["--data-dir", args.data_dir] if args.data_dir else [])
        return 0
    from .service import SolarService

    try:
        svc = SolarService(args.data_dir, interface="cli")
        if args.cmd == "validate":
            out = svc.validate_request(_read_json(args.request))
        elif args.cmd == "pitch":
            out = svc.calculate_row_pitch(_read_json(args.request))
        elif args.cmd == "project":
            if args.pcmd == "create":
                out = svc.create_project(_read_json(args.request), name=args.name)
            elif args.pcmd == "get":
                out = svc.get_project(args.project_id)
            elif args.pcmd == "update":
                out = svc.update_project(args.project_id, args.expected_revision, _read_json(args.request), name=args.name)
            else:
                out = svc.list_projects()
        elif args.cmd == "generate":
            if args.project:
                out = svc.generate_layout(project_id=args.project, revision=args.revision)
            else:
                if not args.request:
                    raise DomainError("INVALID_INPUT", "Give a request file or --project", field="request")
                out = svc.generate_layout(request=_read_json(args.request))
        elif args.cmd == "summary":
            out = svc.get_layout_summary(args.result_id, project_id=args.project)
        elif args.cmd == "items":
            out = svc.get_layout_items(args.result_id, args.kind, offset=args.offset, cursor=args.cursor, limit=args.limit)
        elif args.cmd == "export":
            out = svc.export_layout(args.result_id, args.format)
            out["absolute_path"] = str(svc.store.export_root / out["path"])
        elif args.cmd == "verify":
            out = svc.verify_stored_result(args.result_id)
        else:  # pragma: no cover
            raise DomainError(INTERNAL_ERROR, f"unknown command {args.cmd}")
    except DomainError as e:
        _emit({"ok": False, "error": e.to_dict()})
        return 2
    except FileNotFoundError as e:
        _emit({"ok": False, "error": {"code": "INVALID_INPUT", "message": f"File not found: {e.filename}", "field": "request"}})
        return 2
    _emit({"ok": True, "result": out})
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
