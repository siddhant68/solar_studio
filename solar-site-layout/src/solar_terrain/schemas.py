"""Packaged JSON Schemas (copies of handoffs/module-02-terrain/contracts; a test keeps them identical)."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

import jsonschema

SURFACE = "terrain-surface.schema.json"
REQUEST = "placement-request.schema.json"
RESULT = "placement-result.schema.json"


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    return json.loads(resources.files("solar_terrain").joinpath("schemas", name).read_text())


@lru_cache(maxsize=None)
def validator(name: str, definition: str | None = None) -> jsonschema.Draft202012Validator:
    """Validator for a schema, or for one of its $defs as a standalone schema."""
    schema = load_schema(name)
    if definition is not None:
        schema = dict(schema["$defs"][definition])
    return jsonschema.Draft202012Validator(schema)


def error_path(err: jsonschema.ValidationError) -> str:
    out = ""
    for part in err.absolute_path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out
