"""Strict JSON input and canonical JSON output.

Input: NaN, Infinity and numbers that overflow to infinity are rejected rather than
parsed, so non-finite values never reach validation as floats.

Canonical output (used for every digest): sorted keys, no whitespace, floats written
with Python's shortest round-trip `repr`, -0.0 written as 0.0, integers that came from
float fields kept as floats. Two values with equal canonical text are bit-identical.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .errors import INVALID_INPUT, DomainError


class _NonFinite(ValueError):
    pass


def _reject_constant(name: str) -> float:
    raise _NonFinite(name)


def _parse_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise _NonFinite(text)
    return value


def loads_strict(text: str | bytes) -> Any:
    try:
        return json.loads(text, parse_constant=_reject_constant, parse_float=_parse_float)
    except _NonFinite as exc:
        raise DomainError(
            INVALID_INPUT,
            f"Non-finite number {exc.args[0]!r} is not accepted",
            field="",
            details={"reason": "non_finite_number"},
        ) from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DomainError(INVALID_INPUT, f"Request is not valid JSON: {exc}", field="") from None


def _canon(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float in canonical JSON")
        return 0.0 if value == 0.0 else value
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if hasattr(value, "item"):  # numpy scalar
        return _canon(value.item())
    raise TypeError(f"not JSON serialisable: {type(value)!r}")


def canonical_dumps(value: Any) -> str:
    return json.dumps(_canon(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def digest_of(value: Any) -> str:
    return sha256_hex(canonical_dumps(value))


def fmt_float(value: float) -> str:
    """Shortest round-trip decimal text for CSV/SVG/report numbers (never -0)."""
    value = float(value)
    if value == 0.0:
        return "0.0"
    return repr(value)
