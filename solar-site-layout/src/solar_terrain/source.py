"""The Module 01 inputs of a placement, read through SolarService's published operations.

Only get_layout_summary and get_layout_items are used, and only the fields listed in
CONTRACTS.md section 1. No Module 01 engine module is imported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from solar_layout.errors import SOURCE_MISMATCH, DomainError

PAGE = 500


@dataclass
class SourceLayout:
    result_id: str
    payload_digest: str
    schema_version: str
    algorithm_version: str
    frame: dict[str, Any]
    u: tuple[float, float]
    v: tuple[float, float]
    W: float
    D: float
    H: float
    h0: float
    origin: tuple[float, float]
    tables: list[dict[str, Any]]
    modules: list[dict[str, Any]]


def _all_items(layouts: Any, result_id: str, kind: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = None
    while True:
        page = layouts.get_layout_items(result_id, kind, cursor=cursor, limit=PAGE)
        out.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return out


def check_source(layouts: Any, result_id: str, payload_digest: str) -> dict[str, Any]:
    """The Module 01 summary of the named result: RESULT_NOT_FOUND from Module 01 if it is
    unknown, SOURCE_MISMATCH if the named payload digest is not the stored result's."""
    head = layouts.get_layout_summary(result_id)
    if head["payload_digest"] != payload_digest:
        raise DomainError(
            SOURCE_MISMATCH,
            f"Result {result_id} has payload digest {head['payload_digest']}, not the requested {payload_digest}",
            field="source_layout.payload_digest",
            details={"stored_payload_digest": head["payload_digest"], "requested_payload_digest": payload_digest},
        )
    return head


def load_source(layouts: Any, head: dict[str, Any]) -> SourceLayout:
    s = head["summary"]
    dims = s["dimensions"]
    result_id = head["result_id"]
    return SourceLayout(
        result_id=result_id,
        payload_digest=head["payload_digest"],
        schema_version=s["schema_version"],
        algorithm_version=s["identity"]["algorithm_version"],
        frame=s["frame"],
        u=tuple(s["axes"]["u_table_width_axis"]),
        v=tuple(s["axes"]["v_uphill_axis"]),
        W=float(dims["table_width_W_m"]),
        D=float(dims["table_projected_depth_D_m"]),
        H=float(dims["table_rise_H_m"]),
        h0=float(dims["lower_edge_height_m"]),
        origin=tuple(s["computation_frame"]["origin_world_xy_m"]),
        tables=_all_items(layouts, result_id, "tables"),
        modules=_all_items(layouts, result_id, "modules"),
    )
