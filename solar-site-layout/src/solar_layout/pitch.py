"""Limited two-dimensional row-pitch calculator.

Separate from placement. Model: flat ground, identical coplanar tables at equal
lower-edge height, infinitely long rows, direct sun arriving perpendicular to the rows
from the panel-facing side, at one user-supplied solar elevation alpha.

    D = L cos(beta)                    projected table depth
    H = L sin(beta)                    total rise (not the lower-edge height)
    shadow_clear_gap = H / tan(alpha)
    pitch_at_that_elevation = D + shadow_clear_gap
    recommended_pitch = max(D + minimum_clear_row_gap, pitch_at_that_elevation)

This is a 2D row-spacing estimate at the specified solar elevation. It is not an
all-year shading guarantee, an obstacle shading model or an energy-loss estimate.
"""

from __future__ import annotations

import math
from typing import Any

from . import PITCH_SCHEMA, policy
from .errors import INVALID_INPUT, UNSUPPORTED_INPUT, DomainError, FieldError
from .geometry import sin_cos_tilt
from .validation import non_finite_errors, schema_errors

MODEL = "flat_equal_height_infinite_rows_perpendicular_front_sun"
LABEL = "2D row-spacing estimate at the specified solar elevation"
ASSUMPTIONS = [
    "flat ground",
    "equal lower-edge heights",
    "infinite rows",
    "direct sun perpendicular to the row from the facing side",
    "single specified elevation only",
]
NOT_PROVIDED = [
    "all-year or seasonal shading guarantee",
    "obstacle or terrain shading",
    "energy or shading-loss estimate",
    "solar position from a place, date or time",
]
UNSUPPORTED_KEYS = {
    "solar_azimuth_deg": "Arbitrary solar azimuth is not supported in this release; the model assumes sun perpendicular to the rows",
    "datetime": "Dates and times are not supported; supply the solar elevation directly",
    "date": "Dates and times are not supported; supply the solar elevation directly",
    "time": "Dates and times are not supported; supply the solar elevation directly",
    "time_window": "Date/time windows are not supported in this release",
    "start": "Date/time windows are not supported in this release",
    "end": "Date/time windows are not supported in this release",
    "timezone": "Dates and times are not supported; supply the solar elevation directly",
    "latitude_deg": "Solar position from a location is not computed; supply the solar elevation directly",
    "longitude_deg": "Solar position from a location is not computed; supply the solar elevation directly",
    "location": "Solar position from a location is not computed; supply the solar elevation directly",
    "city": "Solar position from a location is not computed; supply the solar elevation directly",
}
KNOWN_KEYS = {"schema_version", "table_slope_length_m", "tilt_deg", "solar_elevation_deg", "minimum_clear_row_gap_m", "model"}


def calculate_row_pitch(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise DomainError(INVALID_INPUT, "Request must be a JSON object", field="")
    errors = non_finite_errors(raw)
    if errors:
        raise DomainError.from_field_errors(errors)
    unsupported = [
        FieldError(UNSUPPORTED_INPUT, f"/{k}", msg, {"reason": "unsupported_in_this_release"})
        for k, msg in UNSUPPORTED_KEYS.items()
        if k in raw
    ]
    if unsupported:
        raise DomainError.from_field_errors(unsupported)
    unknown = [FieldError(INVALID_INPUT, f"/{k}", f"Unknown field {k!r}", {"reason": "schema:additionalProperties"}) for k in raw if k not in KNOWN_KEYS]
    errors = schema_errors(raw, "solar.row_pitch.request.v1.schema.json") + unknown
    if errors:
        raise DomainError.from_field_errors(errors)
    L = float(raw["table_slope_length_m"])
    beta = float(raw["tilt_deg"])
    alpha = float(raw["solar_elevation_deg"])
    gap = float(raw["minimum_clear_row_gap_m"])
    if not (0.0 < alpha <= 90.0):
        raise DomainError(
            INVALID_INPUT,
            f"Solar elevation must be in (0, 90] degrees; got {alpha}",
            field="/solar_elevation_deg",
            details={"reason": "out_of_range", "minimum_exclusive": 0, "maximum": 90},
        )
    sb, cb = sin_cos_tilt(beta)
    D = L * cb
    H = L * sb
    if H == 0.0:
        shadow = 0.0
    else:
        if alpha < policy.MIN_SOLAR_ELEVATION_DEG:
            bound = H / math.tan(math.radians(policy.MIN_SOLAR_ELEVATION_DEG))
            raise DomainError(
                UNSUPPORTED_INPUT,
                f"Solar elevation {alpha} deg is below the supported minimum {policy.MIN_SOLAR_ELEVATION_DEG} deg for a tilted table; "
                f"the shadow gap grows without bound near the horizon (already {bound:.1f} m at the minimum)",
                field="/solar_elevation_deg",
                details={
                    "reason": "near_horizon",
                    "minimum_supported_elevation_deg": policy.MIN_SOLAR_ELEVATION_DEG,
                    "shadow_clear_gap_at_minimum_m": bound,
                },
            )
        shadow = 0.0 if alpha == 90.0 else H / math.tan(math.radians(alpha))
    at_elevation = D + shadow
    clearance = D + gap
    recommended = max(clearance, at_elevation)
    return {
        "schema_version": "solar.row_pitch.result/1",
        "label": LABEL,
        "model": MODEL,
        "inputs": {
            "table_slope_length_m": L,
            "tilt_deg": beta,
            "solar_elevation_deg": alpha,
            "minimum_clear_row_gap_m": gap,
        },
        "projected_depth_m": D,
        "table_rise_m": H,
        "shadow_clear_gap_m": shadow,
        "pitch_at_that_elevation_m": at_elevation,
        "clearance_pitch_m": clearance,
        "recommended_pitch_m": recommended,
        "governed_by": "solar_elevation" if at_elevation > clearance else ("minimum_clear_row_gap" if clearance > at_elevation else "both_equal"),
        "pitch_definition": "lower edge to lower edge, horizontal, perpendicular to the rows",
        "formulae": {
            "projected_depth_m": "L cos(beta)",
            "table_rise_m": "L sin(beta)",
            "shadow_clear_gap_m": "H / tan(alpha)",
            "pitch_at_that_elevation_m": "D + H / tan(alpha)",
            "recommended_pitch_m": "max(D + minimum_clear_row_gap, D + H / tan(alpha))",
        },
        "assumptions": ASSUMPTIONS,
        "not_provided": NOT_PROVIDED,
    }


assert PITCH_SCHEMA == "solar.row_pitch.request/1"
