"""The shared application service. CLI, HTTP and MCP call these operations and nothing else.

Selection policy (defined before implementation, see docs/CONTRACTS.md):
* A result is immutable and bound to the inputs it was generated from. When generated
  from a project, it records (project_id, revision) as its source.
* Generation never edits the project's specification.
* After generation the service selects the result for the project ONLY if the project is
  still at the source revision (compare-and-swap). If the project moved on meanwhile, the
  result is kept as an explicitly historical result and the newer selection is untouched.
* A project's selected result is reported as current only while its revision equals the
  project's revision; after any edit it is reported as historical/outdated.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import platform
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from . import ALGORITHM_VERSION, GEOMETRY_POLICY_VERSION, RESULT_SCHEMA, __version__, policy
from .errors import INVALID_CURSOR, INVALID_INPUT, VERIFICATION_FAILED, DomainError
from .exports import build_export, check_format, check_result_id, open_export
from .layout import candidate_estimate, compute_layout
from .pitch import calculate_row_pitch
from .result import ResultRecords, result_id_for
from .store import Store, now
from .validation import validate_layout_request
from .verify import verify_records

DEFAULT_PAGE = 100
MAX_PAGE = 500
REPO_ROOT = Path(__file__).resolve().parents[3]


def _dep_versions() -> dict[str, str]:
    import numpy
    import shapely

    out = {"python": platform.python_version(), "shapely": shapely.__version__, "geos": shapely.geos_version_string, "numpy": numpy.__version__}
    for pkg in ("ezdxf", "jsonschema", "starlette", "uvicorn", "mcp"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "not installed"
    return out


def _source_commit() -> tuple[str | None, bool | None]:
    env = os.environ.get("SOLAR_SOURCE_COMMIT")
    if env:
        return env, None
    try:
        head = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        if head.returncode != 0:
            return None, None
        dirty = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--", "solar-site-layout/src"], capture_output=True, text=True, timeout=5
        )
        return head.stdout.strip(), bool(dirty.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None, None


def _encode_cursor(result_id: str, kind: str, seq: int) -> str:
    raw = json.dumps({"r": result_id, "k": kind, "s": seq}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str, result_id: str, kind: str) -> int:
    try:
        pad = "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(cursor + pad))
        seq = data["s"]
        ok = data["r"] == result_id and data["k"] == kind and isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0
    except (ValueError, KeyError, TypeError, binascii.Error):
        ok = False
    if not ok:
        raise DomainError(INVALID_CURSOR, "Cursor is malformed or belongs to a different result or item kind", field="cursor")
    return seq


class SolarService:
    def __init__(self, data_dir: str | os.PathLike | None = None, interface: str = "python"):
        self.store = Store(data_dir or os.environ.get("SOLAR_DATA_DIR", "data"))
        self.interface = interface
        self._deps = _dep_versions()
        self._commit = _source_commit()

    # ---- stateless --------------------------------------------------------------------
    def validate_request(self, request: Any) -> dict[str, Any]:
        try:
            val = validate_layout_request(request)
        except DomainError as e:
            return {"valid": False, "error": e.to_dict()}
        d = val.dims
        return {
            "valid": True,
            "input_digest": val.input_digest,
            "normalized_request": val.normalized,
            "dimensions": {
                "module_w_across_m": d.module_w,
                "module_l_upslope_m": d.module_l,
                "table_width_W_m": d.W,
                "table_slope_length_L_m": d.L,
                "table_projected_depth_D_m": d.D,
                "table_rise_H_m": d.H,
                "modules_per_table": d.modules_per_table,
                "clear_row_gap_m": val.normalized["placement"]["row_pitch_m"] - d.D,
            },
            "axes": {"u": list(val.u), "v": list(val.v)},
            "candidate_bounds": candidate_estimate(val),
            "warnings": val.warnings,
            "limits": policy.LIMITS,
        }

    def calculate_row_pitch(self, request: Any) -> dict[str, Any]:
        return calculate_row_pitch(request)

    # ---- projects ---------------------------------------------------------------------
    def create_project(self, request: Any, name: str | None = None) -> dict[str, Any]:
        val = validate_layout_request(request)
        return self.store.create_project(name or val.normalized.get("name") or "Untitled site", val.normalized, val.input_digest)

    def get_project(self, project_id: str) -> dict[str, Any]:
        if not isinstance(project_id, str):
            raise DomainError(INVALID_INPUT, "project_id must be a string", field="project_id")
        return self.store.get_project(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        return self.store.list_projects()

    def update_project(self, project_id: str, expected_revision: Any, request: Any, name: str | None = None) -> dict[str, Any]:
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
            raise DomainError(INVALID_INPUT, "expected_revision must be a positive integer", field="expected_revision")
        val = validate_layout_request(request)
        current = self.store.get_project(project_id)
        return self.store.update_project(project_id, expected_revision, name or val.normalized.get("name") or current["name"], val.normalized, val.input_digest)

    # ---- layouts ----------------------------------------------------------------------
    def provenance(self, created_at: str) -> dict[str, Any]:
        commit, dirty = self._commit
        return {
            "schema_version": RESULT_SCHEMA,
            "package_version": __version__,
            "algorithm_version": ALGORITHM_VERSION,
            "geometry_policy_version": GEOMETRY_POLICY_VERSION,
            "geometry_policy": policy.GEOMETRY_POLICY,
            "limits": policy.LIMITS,
            "dependencies": self._deps,
            "source_commit": commit,
            "source_dirty": dirty,
            "platform": f"{platform.system()} {platform.machine()}",
            "created_at": created_at,
        }

    def generate_layout(
        self,
        project_id: str | None = None,
        revision: int | None = None,
        request: Any = None,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        source = None
        if project_id is not None:
            if request is not None:
                raise DomainError(INVALID_INPUT, "Give either project_id (with optional revision) or request, not both", field="request")
            if revision is None:
                proj = self.store.get_project(project_id)
                revision = proj["revision"]
                snapshot = proj["request"]
            else:
                if not isinstance(revision, int) or isinstance(revision, bool):
                    raise DomainError(INVALID_INPUT, "revision must be an integer", field="revision")
                snapshot = self.store.get_project_revision(project_id, revision)["request"]
            source = (project_id, revision)
            request = snapshot
        elif request is None:
            raise DomainError(INVALID_INPUT, "Give a project_id or an inline request", field="request")
        val = validate_layout_request(request)
        result_id = result_id_for(val.input_digest)
        reused = self.store.result_exists(result_id)
        if not reused:
            comp = compute_layout(val, timeout_s=timeout_s)
            rr = ResultRecords(comp)
            tables = list(rr.table_records())
            verification = verify_records(val.normalized, rr.summary, tables, rr.module_records())
            if not verification["ok"]:
                raise DomainError(
                    VERIFICATION_FAILED,
                    "The independent verifier rejected the generated layout; nothing was saved",
                    details={"failed_checks": [k for k, v in verification["checks"].items() if not v["ok"]]},
                )
            created_at = now()
            self.store.insert_result(
                result_id=rr.result_id,
                input_digest=val.input_digest,
                payload_digest=rr.payload_digest,
                request=val.normalized,
                summary=rr.summary,
                regions=rr.region_geojson(),
                provenance=self.provenance(created_at),
                verification=verification,
                tables=tables,
                modules=rr.module_records(),
                created_at=created_at,
            )
        selection = "no_project"
        if source:
            self.store.add_result_source(result_id, source[0], source[1], self.interface)
            selected = self.store.select_result_if_current(source[0], source[1], result_id)
            selection = "selected" if selected else "historical_not_selected"
        out = self.get_layout_summary(result_id, project_id=source[0] if source else None)
        out["reused_existing_result"] = reused
        out["selection"] = selection
        out["source"] = {"project_id": source[0], "project_revision": source[1]} if source else None
        return out

    def get_layout_summary(self, result_id: str, project_id: str | None = None) -> dict[str, Any]:
        check_result_id(result_id)
        row = self.store.get_result_row(result_id)
        status = None
        if project_id is not None:
            proj = self.store.get_project(project_id)
            revs = [s["project_revision"] for s in row["sources"] if s["project_id"] == project_id]
            status = {
                "project_id": project_id,
                "project_revision": proj["revision"],
                "result_source_revisions": revs,
                "is_current": proj["revision"] in revs,
                "label": "current" if proj["revision"] in revs else "historical (inputs changed since this result was generated)",
                "is_selected": proj["selected_result_id"] == result_id,
            }
        return {
            "result_id": result_id,
            "input_digest": row["input_digest"],
            "payload_digest": row["payload_digest"],
            "created_at": row["created_at"],
            "summary": row["summary"],
            "provenance": row["provenance"],
            "verification": {"ok": row["verification"]["ok"], "checks": {k: v["ok"] for k, v in row["verification"]["checks"].items()}},
            "sources": row["sources"],
            "exports": row["exports"],
            "project_status": status,
            "items": {
                "tables": {"total": row["table_count"]},
                "modules": {"total": row["module_count"]},
                "default_page_size": DEFAULT_PAGE,
                "max_page_size": MAX_PAGE,
            },
        }

    def get_layout_items(self, result_id: str, kind: str = "modules", offset: int | None = None, cursor: str | None = None, limit: int | None = None) -> dict[str, Any]:
        check_result_id(result_id)
        if kind not in ("tables", "modules"):
            raise DomainError(INVALID_INPUT, "kind must be 'tables' or 'modules'", field="kind")
        if limit is None:
            limit = DEFAULT_PAGE
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > MAX_PAGE:
            raise DomainError(INVALID_CURSOR, f"limit must be an integer in 1..{MAX_PAGE}; pages are never silently truncated", field="limit", details={"max_page_size": MAX_PAGE})
        if offset is not None and cursor is not None:
            raise DomainError(INVALID_CURSOR, "Give offset or cursor, not both", field="cursor")
        row = self.store.get_result_row(result_id)
        total = row["table_count"] if kind == "tables" else row["module_count"]
        if cursor is not None:
            start = _decode_cursor(cursor, result_id, kind)
        else:
            start = 0 if offset is None else offset
            if not isinstance(start, int) or isinstance(start, bool) or start < 0:
                raise DomainError(INVALID_CURSOR, "offset must be a non-negative integer", field="offset")
        if start > total:
            raise DomainError(INVALID_CURSOR, f"Start {start} is beyond the {total} {kind} in this result", field="offset" if cursor is None else "cursor", details={"total": total})
        items = self.store.page(result_id, kind, start, limit)
        nxt = start + len(items)
        return {
            "result_id": result_id,
            "kind": kind,
            "offset": start,
            "limit": limit,
            "total": total,
            "items": items,
            "next_cursor": _encode_cursor(result_id, kind, nxt) if nxt < total else None,
            "next_offset": nxt if nxt < total else None,
        }

    def export_layout(self, result_id: str, format: str) -> dict[str, Any]:
        check_result_id(result_id)
        check_format(format)
        self.store.get_result_row(result_id)  # RESULT_NOT_FOUND
        return build_export(self.store, result_id, format)

    def open_export(self, result_id: str, format: str):
        """Publish or reuse an export and return (open verified handle, metadata)."""
        check_result_id(result_id)
        check_format(format)
        self.store.get_result_row(result_id)  # RESULT_NOT_FOUND
        return open_export(self.store, result_id, format)

    def verify_stored_result(self, result_id: str) -> dict[str, Any]:
        check_result_id(result_id)
        row = self.store.get_result_row(result_id)
        return verify_records(row["request"], row["summary"], self.store.iter_records(result_id, "tables"), self.store.iter_records(result_id, "modules"))
