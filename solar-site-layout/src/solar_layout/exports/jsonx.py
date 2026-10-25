"""JSON export: normalized inputs, provenance, summary, regions and all geometry.

Streamed record by record so large results are never held as one string.
"""

from __future__ import annotations

import json
from typing import IO, Any, Iterable

from ..jsonio import canonical_dumps

EXPORT_SCHEMA = "solar.layout.export/1"


def write_json(
    out: IO[str],
    request: dict[str, Any],
    summary: dict[str, Any],
    provenance: dict[str, Any],
    regions: dict[str, Any],
    tables: Iterable[dict[str, Any]],
    modules: Iterable[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> None:
    out.write("{\n")
    out.write(f'"schema_version": {json.dumps(EXPORT_SCHEMA)},\n')
    out.write('"note": "Coordinates are metres in the request frame (x East, y North); this is not RFC 7946 geographic GeoJSON. z values are relative to the layout\'s synthetic flat datum.",\n')
    out.write(f'"request": {canonical_dumps(request)},\n')
    out.write(f'"result": {canonical_dumps(summary)},\n')
    out.write(f'"provenance": {canonical_dumps(provenance)},\n')
    out.write(f'"project_sources": {canonical_dumps(sources)},\n')
    out.write(f'"regions": {canonical_dumps(regions)},\n')
    out.write('"tables": [')
    first = True
    for t in tables:
        out.write(("\n" if first else ",\n") + canonical_dumps(t))
        first = False
    out.write("\n],\n")
    out.write('"modules": [')
    first = True
    for m in modules:
        out.write(("\n" if first else ",\n") + canonical_dumps(m))
        first = False
    out.write("\n]\n}\n")
