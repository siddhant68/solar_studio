"""Local HTTP API and browser interface (Starlette). Binds to loopback by default.

Success bodies are the service result as JSON. Errors use
    {"error": {"code", "message", "field"?, "details"?, "errors"?}}
with the HTTP status from errors.HTTP_STATUS; the domain `code` is identical to the CLI's
and MCP's.
"""

from __future__ import annotations

import os
from importlib import resources
from typing import Any

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .errors import HTTP_STATUS, INTERNAL_ERROR, INVALID_INPUT, RESOURCE_LIMIT, DomainError
from .exports import MEDIA_TYPES, export_path, verify_export_file
from .jsonio import loads_strict
from .service import SolarService

MAX_BODY_BYTES = 20 * 1024 * 1024


def _error(e: DomainError) -> JSONResponse:
    return JSONResponse({"error": e.to_dict()}, status_code=HTTP_STATUS.get(e.code, 500))


async def _body(request: Request) -> Any:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise DomainError(RESOURCE_LIMIT, f"Request body exceeds {MAX_BODY_BYTES} bytes", details={"limit": "max_body_bytes"})
    if not raw:
        raise DomainError(INVALID_INPUT, "Request body is empty", field="")
    return loads_strict(raw)


def _int_param(request: Request, name: str) -> int | None:
    v = request.query_params.get(name)
    if v is None or v == "":
        return None
    try:
        return int(v)
    except ValueError:
        raise DomainError("INVALID_CURSOR" if name in ("offset", "limit") else INVALID_INPUT, f"{name} must be an integer", field=name) from None


def create_app(data_dir: str | None = None) -> Starlette:
    svc = SolarService(data_dir, interface="http")

    def handler(fn):
        async def endpoint(request: Request):
            try:
                result = await fn(request)
            except DomainError as e:
                return _error(e)
            except Exception as e:  # pragma: no cover - surfaced as typed internal error
                return _error(DomainError(INTERNAL_ERROR, f"Internal error: {type(e).__name__}"))
            if isinstance(result, Response):
                return result
            return JSONResponse(result)

        return endpoint

    async def health(request: Request):
        return {"ok": True, "data_dir": str(svc.store.data_dir)}

    async def validate(request: Request):
        return await run_in_threadpool(svc.validate_request, await _body(request))

    async def pitch(request: Request):
        return await run_in_threadpool(svc.calculate_row_pitch, await _body(request))

    async def projects(request: Request):
        if request.method == "GET":
            return {"projects": await run_in_threadpool(svc.list_projects)}
        body = await _body(request)
        if not isinstance(body, dict) or "request" not in body:
            raise DomainError(INVALID_INPUT, "Body must be {\"request\": {...}, \"name\"?: string}", field="request")
        return await run_in_threadpool(svc.create_project, body["request"], body.get("name"))

    async def project(request: Request):
        pid = request.path_params["project_id"]
        if request.method == "GET":
            return await run_in_threadpool(svc.get_project, pid)
        body = await _body(request)
        if not isinstance(body, dict) or "request" not in body or "expected_revision" not in body:
            raise DomainError(INVALID_INPUT, "Body must be {\"expected_revision\": int, \"request\": {...}, \"name\"?: string}", field="")
        return await run_in_threadpool(svc.update_project, pid, body["expected_revision"], body["request"], body.get("name"))

    async def layouts(request: Request):
        body = await _body(request)
        if not isinstance(body, dict):
            raise DomainError(INVALID_INPUT, "Body must be an object", field="")
        return await run_in_threadpool(
            lambda: svc.generate_layout(project_id=body.get("project_id"), revision=body.get("revision"), request=body.get("request"))
        )

    async def layout(request: Request):
        return await run_in_threadpool(svc.get_layout_summary, request.path_params["result_id"], request.query_params.get("project_id"))

    async def items(request: Request):
        rid = request.path_params["result_id"]
        return await run_in_threadpool(
            svc.get_layout_items,
            rid,
            request.query_params.get("kind", "modules"),
            _int_param(request, "offset"),
            request.query_params.get("cursor"),
            _int_param(request, "limit"),
        )

    async def export(request: Request):
        rid = request.path_params["result_id"]
        fmt = request.path_params["fmt"]
        if request.method == "POST":
            return await run_in_threadpool(svc.export_layout, rid, fmt)
        rec = await run_in_threadpool(svc.store.get_export, rid, fmt) if fmt in MEDIA_TYPES else None
        if rec is None:
            await run_in_threadpool(svc.export_layout, rid, fmt)
        path = await run_in_threadpool(verify_export_file, svc.store, rid, fmt)
        _, rel = export_path(svc.store, rid, fmt)
        return FileResponse(path, media_type=MEDIA_TYPES[fmt], filename=path.name, headers={"X-Content-SHA256": (await run_in_threadpool(svc.store.get_export, rid, fmt))["sha256"]})

    async def plan_svg(request: Request):
        rid = request.path_params["result_id"]
        if await run_in_threadpool(svc.store.get_export, rid, "svg") is None:
            await run_in_threadpool(svc.export_layout, rid, "svg")
        path = await run_in_threadpool(verify_export_file, svc.store, rid, "svg")
        return FileResponse(path, media_type="image/svg+xml")

    async def index(request: Request):
        html = resources.files("solar_layout").joinpath("web", "index.html").read_text()
        return Response(html, media_type="text/html; charset=utf-8")

    web_dir = str(resources.files("solar_layout").joinpath("web"))
    routes = [
        Route("/", handler(index)),
        Route("/api/health", handler(health)),
        Route("/api/validate", handler(validate), methods=["POST"]),
        Route("/api/row-pitch", handler(pitch), methods=["POST"]),
        Route("/api/projects", handler(projects), methods=["GET", "POST"]),
        Route("/api/projects/{project_id}", handler(project), methods=["GET", "PUT"]),
        Route("/api/layouts", handler(layouts), methods=["POST"]),
        Route("/api/layouts/{result_id}", handler(layout)),
        Route("/api/layouts/{result_id}/items", handler(items)),
        Route("/api/layouts/{result_id}/plan.svg", handler(plan_svg)),
        Route("/api/layouts/{result_id}/exports/{fmt}", handler(export), methods=["GET", "POST"]),
        Mount("/static", app=StaticFiles(directory=web_dir), name="static"),
    ]
    app = Starlette(routes=routes)
    app.state.service = svc
    return app


def serve(host: str = "127.0.0.1", port: int = 8765, data_dir: str | None = None) -> None:
    import uvicorn

    uvicorn.run(create_app(data_dir), host=host, port=port, log_level=os.environ.get("SOLAR_LOG_LEVEL", "warning"))
