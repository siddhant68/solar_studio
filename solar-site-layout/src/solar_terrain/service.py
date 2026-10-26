"""TerrainService: the terrain operations shared by the CLI, HTTP and MCP adapters.

It is composed with Module 01's SolarService and reads layouts only through its published
operations (get_layout_summary, get_layout_items). Imports and placements are immutable
and content-addressed; repeating one reuses the stored row.

Placement pipeline: request validation -> source (RESULT_NOT_FOUND, SOURCE_MISMATCH) ->
terrain (TERRAIN_NOT_FOUND) -> frame (FRAME_MISMATCH) -> vertical reference
(DATUM_MISMATCH) -> supports inside the table (INVALID_INPUT) -> engine -> independent
verifier (VERIFICATION_FAILED; nothing stored) -> one transaction. The time limit
(SOLAR_TERRAIN_TIMEOUT_S) is checked between stages and between tables, and once more
before anything is written.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import time
from typing import Any, Callable

from solar_layout.errors import (
    DATUM_MISMATCH,
    FRAME_MISMATCH,
    INVALID_CURSOR,
    INVALID_INPUT,
    RESOURCE_LIMIT,
    TERRAIN_NOT_FOUND,
    VERIFICATION_FAILED,
    DomainError,
)

from . import ALGORITHM_VERSION, POLICY_VERSION, RESULT_SCHEMA, TERRAIN_SCHEMA, __version__, policy
from .engine import TerrainArrays, payload_digest, place
from .exports import build_export, check_format, check_placement_id, open_export
from .provenance import dependency_versions, platform_text, source_commit
from .request import normalize_request, parameters_digest, placement_id_for
from .source import check_source, load_source
from .store import TerrainStore, now
from .surface import normalize_frame, normalize_vertical, validate_surface
from .verify import verify_placement

DEFAULT_PAGE = 100
MAX_PAGE = 500
KINDS = ("tables", "modules", "supports")
TERRAIN_ID_RE = re.compile(r"^ter_[0-9a-f]{24}$")


def _deadline(stage_prefix: str) -> Callable[[str], None]:
    limit = policy.timeout_s()
    start = time.monotonic()

    def check(stage: str) -> None:
        elapsed = time.monotonic() - start
        if limit <= 0 or elapsed > limit:
            raise DomainError(
                RESOURCE_LIMIT,
                f"{stage_prefix} exceeded the time limit of {limit} s (at {stage}); nothing was stored",
                details={"limit": "timeout_s", "timeout_s": limit, "stage": stage},
            )

    return check


def _encode_cursor(placement_id: str, kind: str, seq: int) -> str:
    raw = json.dumps({"p": placement_id, "k": kind, "s": seq}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: Any, placement_id: str, kind: str) -> int:
    try:
        pad = "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(cursor + pad))
        seq = data["s"]
        ok = data["p"] == placement_id and data["k"] == kind and isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0
    except (ValueError, KeyError, TypeError, binascii.Error):
        ok = False
    if not ok:
        raise DomainError(INVALID_CURSOR, "Cursor is malformed or belongs to a different placement or item kind", field="cursor")
    return seq


def check_terrain_id(terrain_id: Any) -> str:
    if not isinstance(terrain_id, str) or not TERRAIN_ID_RE.match(terrain_id):
        raise DomainError(TERRAIN_NOT_FOUND, "Malformed terrain ID; expected ter_ followed by 24 hex digits", field="terrain_id")
    return terrain_id


def _frame_key(frame: dict[str, Any]) -> dict[str, Any]:
    f = normalize_frame(frame)
    return {k: f.get(k) for k in ("kind", "id", "crs", "units", "axes")}


class TerrainService:
    def __init__(self, layouts: Any, data_dir: str | os.PathLike | None = None, interface: str = "python"):
        self.layouts = layouts
        self.store = TerrainStore(data_dir or os.environ.get("SOLAR_DATA_DIR", "data"))
        self.interface = interface
        self._deps = dependency_versions()
        self._commit = source_commit()

    def _provenance(self, created_at: str) -> dict[str, Any]:
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "policy_version": POLICY_VERSION,
            "schema_version": RESULT_SCHEMA,
            "software_version": __version__,
            "source_commit": self._commit[0],
            "source_tree_dirty": self._commit[1],
            "dependencies": self._deps,
            "platform": platform_text(),
            "created_at": created_at,
        }

    # ---- terrains ---------------------------------------------------------------------------
    def validate_terrain(self, surface: Any) -> dict[str, Any]:
        try:
            prepared = validate_surface(surface, _deadline("Terrain validation"))
        except DomainError as e:
            return {"valid": False, "error": e.to_dict()}
        return {
            "valid": True,
            "terrain_id": prepared.terrain_id,
            "terrain_digest": prepared.terrain_digest,
            "frame": prepared.frame,
            "vertical": prepared.vertical,
            "info": prepared.info,
            "limits": policy.LIMITS,
            "already_imported": self.store.terrain_exists(prepared.terrain_id),
        }

    def import_terrain(self, surface: Any) -> dict[str, Any]:
        check = _deadline("Terrain import")
        prepared = validate_surface(surface, check)
        reused = self.store.terrain_exists(prepared.terrain_id)
        if not reused:
            check("before storing the terrain")
            created_at = now()
            prov = {"software_version": __version__, "schema_version": TERRAIN_SCHEMA, "source_commit": self._commit[0], "source_tree_dirty": self._commit[1], "dependencies": self._deps, "platform": platform_text(), "created_at": created_at}
            reused = not self.store.insert_terrain(prepared, prov, TERRAIN_SCHEMA, created_at)
        out = self.get_terrain(prepared.terrain_id)
        out["reused_existing_terrain"] = reused
        return out

    def get_terrain(self, terrain_id: Any) -> dict[str, Any]:
        check_terrain_id(terrain_id)
        row = self.store.get_terrain_row(terrain_id)
        return {
            "terrain_id": row["terrain_id"],
            "terrain_digest": row["terrain_digest"],
            "schema_version": row["schema_version"],
            "name": row["name"],
            "source": row["source"],
            "frame": row["frame"],
            "vertical": row["vertical"],
            "info": row["info"],
            "provenance": row["provenance"],
            "created_at": row["created_at"],
            "identity": {"terrain_id_derivation": "ter_ + sha256('solar.terrain.surface/1|' + terrain_digest)[:24]; terrain_digest = sha256(canonical {frame, vertical, vertices_xyz_m, triangles}); name and source are not part of the identity"},
        }

    def _terrain_arrays(self, row: dict[str, Any]) -> TerrainArrays:
        arrays = self.store.load_arrays(row["terrain_id"])
        return TerrainArrays(
            terrain_id=row["terrain_id"],
            terrain_digest=row["terrain_digest"],
            frame=row["frame"],
            vertical=row["vertical"],
            vertices=arrays["vertices"],
            triangles=arrays["triangles"],
            boundary_segments=arrays["boundary_segments"],
        )

    # ---- placements -------------------------------------------------------------------------
    def _resolve(self, request: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str]:
        """Validate a request against its sources; return (normalized request, Module 01
        summary head, terrain row, parameters digest, placement ID)."""
        norm = normalize_request(request)
        src = norm["source_layout"]
        head = check_source(self.layouts, src["result_id"], src["payload_digest"])
        terrain = self.store.get_terrain_row(norm["terrain"])
        lf, tf = _frame_key(head["summary"]["frame"]), _frame_key(terrain["frame"])
        if lf != tf:
            diff = sorted(k for k in lf if lf[k] != tf[k])
            raise DomainError(
                FRAME_MISMATCH,
                f"The terrain frame differs from the layout frame in {diff}; no horizontal transformation is performed",
                field="terrain",
                details={"layout_frame": lf, "terrain_frame": tf, "differs_in": diff},
            )
        ev = norm.get("expected_vertical")
        if ev is not None:
            tv = normalize_vertical(terrain["vertical"])
            have = {"kind": tv["kind"], "crs": tv.get("crs"), "id": tv.get("id")}
            want = {"kind": ev["kind"], "crs": ev.get("crs"), "id": ev.get("id")}
            if have != want:
                raise DomainError(
                    DATUM_MISMATCH,
                    f"expected_vertical {want} differs from the terrain's vertical reference {have}; no vertical transformation is performed",
                    field="expected_vertical",
                    details={"expected": want, "terrain": have},
                )
        dims = head["summary"]["dimensions"]
        W, D = float(dims["table_width_W_m"]), float(dims["table_projected_depth_D_m"])
        errors = []
        for k, (a, d) in enumerate(norm["supports"]["points_ad_m"]):
            if not (0.0 <= a <= W and 0.0 <= d <= D):
                errors.append(f"supports.points_ad_m[{k}] = [{a!r}, {d!r}] is outside the table (0 <= a <= {W!r}, 0 <= d <= {D!r})")
        if errors:
            raise DomainError(INVALID_INPUT, errors[0], field="supports.points_ad_m", details={"errors": errors, "table_width_W_m": W, "table_projected_depth_D_m": D})
        params = parameters_digest(norm)
        pid = placement_id_for(src["result_id"], src["payload_digest"], terrain["terrain_digest"], params)
        return norm, head, terrain, params, pid

    def place_on_terrain(self, request: Any) -> dict[str, Any]:
        check = _deadline("Terrain placement")
        norm, head, terrain, params, pid = self._resolve(request)
        reused = self.store.placement_exists(pid)
        if not reused:
            check("request validation")
            src = load_source(self.layouts, head)
            ter = self._terrain_arrays(terrain)
            check("loading the layout and terrain")
            pl = place(src, ter, norm, check)
            summary = {
                "schema_version": RESULT_SCHEMA,
                "placement_id": pid,
                "source_layout": {"result_id": src.result_id, "payload_digest": src.payload_digest, "schema_version": src.schema_version, "algorithm_version": src.algorithm_version},
                "terrain": {"terrain_id": terrain["terrain_id"], "terrain_digest": terrain["terrain_digest"]},
                "parameters_digest": params,
                "frame": normalize_frame(terrain["frame"]),
                "vertical": normalize_vertical(terrain["vertical"]),
                "z_kind": "terrain_vertical_reference",
                "policy": {
                    "policy": norm["placement"]["policy"],
                    "minimum_clearance_m": norm["placement"]["minimum_clearance_m"],
                    "structure_depth_m": norm["placement"]["structure_depth_m"],
                    "supports_model": norm["supports"]["model"],
                    "limits": norm["limits"],
                    "coverage": norm["coverage"],
                    "numerical_policy": POLICY_VERSION,
                },
                "counts": pl.counts,
                "statistics": pl.statistics,
                "diagnostics": pl.diagnostics,
                "warnings": pl.warnings,
                "not_computed": list(policy.NOT_COMPUTED),
                "provenance": self._provenance(now()),
                "verification": {"ok": True, "checks": {}},
            }
            summary["payload_digest"] = payload_digest(summary, pl.tables, pl.modules, pl.supports)
            check("placement")
            result = verify_placement(src, terrain, ter.vertices, ter.triangles, norm, summary, pl.tables, pl.modules, pl.supports)
            if not result["ok"]:
                raise DomainError(
                    VERIFICATION_FAILED,
                    "The independent verifier rejected the placement; nothing was saved",
                    details={"failed_checks": {k: v["failures"] for k, v in result["checks"].items() if not v["ok"]}},
                )
            summary["verification"] = {
                "ok": True,
                "verifier": "solar_terrain.verify, independent of the engine (own candidate grid, exact arithmetic, clipping and boundary reconstruction)",
                "checks": {k: {"ok": v["ok"]} for k, v in result["checks"].items()},
                "candidates": result["candidates"],
                "exact_rational_evaluations": result["exact_rational_evaluations"],
            }
            check("independent verification")
            reused = not self.store.insert_placement(
                pid, summary["payload_digest"], terrain["terrain_id"], src.result_id, src.payload_digest, norm, summary, pl.tables, pl.modules, pl.supports, summary["provenance"]["created_at"]
            )
        out = self.get_placement_summary(pid)
        out["reused_existing_placement"] = reused
        return out

    def get_placement_summary(self, placement_id: Any) -> dict[str, Any]:
        check_placement_id(placement_id)
        row = self.store.get_placement_row(placement_id)
        return {
            "placement_id": placement_id,
            "payload_digest": row["payload_digest"],
            "terrain_id": row["terrain_id"],
            "source_layout": {"result_id": row["source_result_id"], "payload_digest": row["source_payload_digest"]},
            "created_at": row["created_at"],
            "request": row["request"],
            "summary": row["summary"],
            "verification": {"ok": row["summary"]["verification"]["ok"], "checks": {k: v["ok"] for k, v in row["summary"]["verification"]["checks"].items()}},
            "exports": row["exports"],
            "items": {
                "tables": {"total": row["table_count"]},
                "modules": {"total": row["module_count"]},
                "supports": {"total": row["support_count"]},
                "default_page_size": DEFAULT_PAGE,
                "max_page_size": MAX_PAGE,
            },
        }

    def get_placement_items(self, placement_id: Any, kind: str = "tables", offset: int | None = None, cursor: str | None = None, limit: int | None = None) -> dict[str, Any]:
        check_placement_id(placement_id)
        if kind not in KINDS:
            raise DomainError(INVALID_INPUT, f"kind must be one of {list(KINDS)}", field="kind")
        if limit is None:
            limit = DEFAULT_PAGE
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > MAX_PAGE:
            raise DomainError(INVALID_CURSOR, f"limit must be an integer in 1..{MAX_PAGE}; pages are never silently truncated", field="limit", details={"max_page_size": MAX_PAGE})
        if offset is not None and cursor is not None:
            raise DomainError(INVALID_CURSOR, "Give offset or cursor, not both", field="cursor")
        row = self.store.get_placement_row(placement_id)
        total = {"tables": row["table_count"], "modules": row["module_count"], "supports": row["support_count"]}[kind]
        if cursor is not None:
            start = _decode_cursor(cursor, placement_id, kind)
        else:
            start = 0 if offset is None else offset
            if not isinstance(start, int) or isinstance(start, bool) or start < 0:
                raise DomainError(INVALID_CURSOR, "offset must be a non-negative integer", field="offset")
        if start > total:
            raise DomainError(INVALID_CURSOR, f"Start {start} is beyond the {total} {kind} in this placement", field="offset" if cursor is None else "cursor", details={"total": total})
        items = self.store.page(placement_id, kind, start, limit)
        nxt = start + len(items)
        return {
            "placement_id": placement_id,
            "kind": kind,
            "offset": start,
            "limit": limit,
            "total": total,
            "items": items,
            "next_cursor": _encode_cursor(placement_id, kind, nxt) if nxt < total else None,
            "next_offset": nxt if nxt < total else None,
        }

    def export_placement(self, placement_id: Any, format: Any) -> dict[str, Any]:
        check_placement_id(placement_id)
        check_format(format)
        self.store.get_placement_row(placement_id)  # PLACEMENT_NOT_FOUND
        return build_export(self.store, placement_id, format)

    def open_export(self, placement_id: Any, format: Any):
        check_placement_id(placement_id)
        check_format(format)
        self.store.get_placement_row(placement_id)
        return open_export(self.store, placement_id, format)

    def verify_stored_placement(self, placement_id: Any) -> dict[str, Any]:
        """Re-run the independent verifier on the stored records against the current Module 01
        records and the stored terrain."""
        check_placement_id(placement_id)
        row = self.store.get_placement_row(placement_id)
        terrain = self.store.get_terrain_row(row["terrain_id"])
        head = check_source(self.layouts, row["source_result_id"], row["source_payload_digest"])
        src = load_source(self.layouts, head)
        ter = self._terrain_arrays(terrain)
        result = verify_placement(
            src,
            terrain,
            ter.vertices,
            ter.triangles,
            row["request"],
            row["summary"],
            self.store.iter_records(placement_id, "tables"),
            self.store.iter_records(placement_id, "modules"),
            self.store.iter_records(placement_id, "supports"),
        )
        result["placement_id"] = placement_id
        return result
