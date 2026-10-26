"""Placement request validation, normalization and identity (CONTRACTS.md section 3).

Checks here need only the request. Checks that need the source layout or the terrain
(support range, frame, vertical reference) are made by the service once both are loaded.
"""

from __future__ import annotations

from typing import Any

from solar_layout.errors import INVALID_INPUT, UNSUPPORTED_OPERATION, DomainError, FieldError
from solar_layout.jsonio import digest_of, sha256_hex

from . import ALGORITHM_VERSION, POLICY_VERSION, REQUEST_SCHEMA, RESULT_SCHEMA
from .schemas import REQUEST, error_path, validator

POLICIES = ("minimum_clearance_vertical_lift",)
SUPPORT_MODELS = ("explicit_table_local",)


def normalize_expected_vertical(ev: dict[str, Any] | None) -> dict[str, Any] | None:
    if ev is None:
        return None
    out = {"kind": ev["kind"], "crs": ev.get("crs")}
    if "id" in ev:
        out["id"] = ev["id"]
    return out


def normalize_request(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict):
        raise DomainError(INVALID_INPUT, "A placement request must be a JSON object", field="")
    errors = []
    for err in sorted(validator(REQUEST).iter_errors(doc), key=lambda e: (list(map(str, e.absolute_path)), e.message)):
        path = error_path(err)
        errors.append(FieldError(INVALID_INPUT, path, f"{path or 'request'}: {err.message}", {"reason": "schema"}))
    if errors:
        raise DomainError.from_field_errors(errors[:20])
    policy = doc["placement"]["policy"]
    if policy not in POLICIES:
        raise DomainError(UNSUPPORTED_OPERATION, f"Placement policy {policy!r} is not supported in T1; use one of {list(POLICIES)}", field="placement.policy", details={"supported": list(POLICIES)})
    model = doc["supports"]["model"]
    if model not in SUPPORT_MODELS:
        raise DomainError(UNSUPPORTED_OPERATION, f"Support model {model!r} is not supported in T1; use one of {list(SUPPORT_MODELS)}", field="supports.model", details={"supported": list(SUPPORT_MODELS)})
    out = {
        "schema_version": REQUEST_SCHEMA,
        "source_layout": {"result_id": doc["source_layout"]["result_id"], "payload_digest": doc["source_layout"]["payload_digest"]},
        "terrain": doc["terrain"],
        "placement": {
            "policy": policy,
            "minimum_clearance_m": float(doc["placement"]["minimum_clearance_m"]),
            "structure_depth_m": float(doc["placement"]["structure_depth_m"]),
        },
        "supports": {"model": model, "points_ad_m": [[float(a), float(d)] for a, d in doc["supports"]["points_ad_m"]]},
        "limits": {
            "max_ground_slope_deg": float(doc["limits"]["max_ground_slope_deg"]),
            "max_support_above_ground_m": float(doc["limits"]["max_support_above_ground_m"]),
        },
        "coverage": doc["coverage"],
    }
    if "expected_vertical" in doc:
        out["expected_vertical"] = normalize_expected_vertical(doc["expected_vertical"])
    return out


def parameters_digest(norm: dict[str, Any]) -> str:
    return digest_of(
        {
            "placement": norm["placement"],
            "supports": norm["supports"],
            "limits": norm["limits"],
            "coverage": norm["coverage"],
            "expected_vertical": norm.get("expected_vertical"),
        }
    )


def placement_id_for(result_id: str, payload_digest: str, terrain_digest: str, params_digest: str) -> str:
    seed = "|".join([RESULT_SCHEMA, ALGORITHM_VERSION, POLICY_VERSION, result_id, payload_digest, terrain_digest, params_digest])
    return "plc_" + sha256_hex(seed)[:24]
