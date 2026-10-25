"""Export orchestration: one immutable result -> files inside the managed export root.

Every file is written to a temporary name in its final directory, flushed and fsynced,
then atomically renamed; only after that is the export recorded in the store. A crash at
any point leaves either no file or an unreferenced `*.partial` file, never a recorded
export pointing at incomplete bytes. Paths are built only from a validated result ID and
an allow-listed format and are checked to stay inside the export root.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Callable

from ..errors import INVALID_INPUT, RESULT_NOT_FOUND, DomainError
from ..jsonio import canonical_dumps
from ..store import Store, fault_point
from .csvx import write_csv
from .dxf import build_dxf
from .jsonx import write_json
from .report import write_report
from .svg import write_svg

RESULT_ID_RE = re.compile(r"^res_[0-9a-f]{24}$")
FORMATS = {
    "json": "layout.json",
    "csv": "modules.csv",
    "svg": "plan.svg",
    "dxf": "plan.dxf",
    "report": "report.md",
    "bundle": "bundle.zip",
}
MEDIA_TYPES = {
    "json": "application/json",
    "csv": "text/csv; charset=utf-8",
    "svg": "image/svg+xml",
    "dxf": "application/dxf",
    "report": "text/markdown; charset=utf-8",
    "bundle": "application/zip",
}


def check_result_id(result_id: Any) -> str:
    if not isinstance(result_id, str) or not RESULT_ID_RE.match(result_id):
        raise DomainError(RESULT_NOT_FOUND, "Malformed result ID; expected res_ followed by 24 hex digits", field="result_id")
    return result_id


def check_format(fmt: Any) -> str:
    if not isinstance(fmt, str) or fmt not in FORMATS:
        raise DomainError(INVALID_INPUT, f"Unsupported export format {fmt!r}; use one of {sorted(FORMATS)}", field="format", details={"supported": sorted(FORMATS)})
    return fmt


def export_path(store: Store, result_id: str, fmt: str) -> tuple[Path, str]:
    check_result_id(result_id)
    check_format(fmt)
    rel = f"{result_id}/{result_id}-{FORMATS[fmt]}"
    path = (store.export_root / rel).resolve()
    if not path.is_relative_to(store.export_root):
        raise DomainError(INVALID_INPUT, "Export path escapes the managed export root", field="format")
    return path, rel


def _atomic_write(path: Path, writer: Callable[[Any], None], binary: bool) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.partial")
    h = hashlib.sha256()
    size = 0
    with open(tmp, "wb") as fh:

        class _Tee(io.RawIOBase):
            def writable(self):
                return True

            def write(self, b):
                nonlocal size
                h.update(b)
                size += len(b)
                fh.write(b)
                return len(b)

        raw = _Tee()
        if binary:
            writer(raw)
        else:
            text = io.TextIOWrapper(io.BufferedWriter(raw, buffer_size=1 << 16), encoding="utf-8", newline="")
            writer(text)
            text.flush()
            text.detach()
        fault_point("export:before_rename")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return h.hexdigest(), size


def build_export(store: Store, result_id: str, fmt: str) -> dict[str, Any]:
    path, rel = export_path(store, result_id, fmt)
    row = store.get_result_row(result_id)
    request = row["request"]
    summary = row["summary"]
    provenance = row["provenance"]
    sources = row["sources"]
    regions = store.get_regions(result_id)

    def tables():
        return store.iter_records(result_id, "tables")

    def modules():
        return store.iter_records(result_id, "modules")

    if fmt == "json":
        digest, size = _atomic_write(path, lambda f: write_json(f, request, summary, provenance, regions, tables(), modules(), sources), False)
    elif fmt == "csv":
        digest, size = _atomic_write(path, lambda f: write_csv(f, modules()), False)
    elif fmt == "svg":
        digest, size = _atomic_write(path, lambda f: write_svg(f, request, summary, regions, tables(), modules(), sources), False)
    elif fmt == "report":
        digest, size = _atomic_write(path, lambda f: write_report(f, request, summary, provenance, sources), False)
    elif fmt == "dxf":
        doc = build_dxf(request, summary, regions, tables(), modules())
        digest, size = _atomic_write(path, lambda f: _write_dxf(doc, f), True)
    else:  # bundle
        parts = {}
        for sub in ("json", "csv", "svg", "dxf", "report"):
            parts[sub] = build_export(store, result_id, sub)
        manifest = {
            "schema_version": "solar.layout.export-bundle/1",
            "result_id": result_id,
            "input_digest": row["input_digest"],
            "payload_digest": row["payload_digest"],
            "frame": summary["frame"],
            "z_kind": summary["z_kind"],
            "versions": {
                "schema_version": provenance["schema_version"],
                "algorithm_version": provenance["algorithm_version"],
                "geometry_policy_version": provenance["geometry_policy_version"],
                "source_commit": provenance.get("source_commit"),
                "dependencies": provenance.get("dependencies"),
            },
            "files": [
                {"name": FORMATS[sub], "format": sub, "sha256": parts[sub]["sha256"], "bytes": parts[sub]["bytes"]} for sub in parts
            ],
        }

        def write_zip(f):
            with zipfile.ZipFile(f, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for sub in parts:
                    p, _ = export_path(store, result_id, sub)
                    info = zipfile.ZipInfo(FORMATS[sub], date_time=(2026, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    with open(p, "rb") as src, z.open(info, "w") as dst:
                        while chunk := src.read(1 << 20):
                            dst.write(chunk)
                info = zipfile.ZipInfo("manifest.json", date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, json.dumps(manifest, indent=1, sort_keys=True))

        digest, size = _atomic_write(path, write_zip, True)
    store.record_export(result_id, fmt, rel, digest, size)
    return {"result_id": result_id, "format": fmt, "path": rel, "file_name": path.name, "sha256": digest, "bytes": size, "media_type": MEDIA_TYPES[fmt]}


def _write_dxf(doc, raw) -> None:
    """Deterministic bytes: ezdxf otherwise stamps write time and fresh GUIDs, which would
    make re-exports of the same immutable result differ. Its fixed-metadata switch writes a
    constant timestamp and GUIDs instead; geometry and layers are unaffected."""
    import ezdxf

    previous = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    try:
        text = io.TextIOWrapper(io.BufferedWriter(raw, buffer_size=1 << 16), encoding="utf-8", newline="")
        doc.write(text)
        text.flush()
        text.detach()
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = previous


def verify_export_file(store: Store, result_id: str, fmt: str) -> Path:
    """Return the file path of a recorded export after checking its bytes still match."""
    rec = store.get_export(result_id, fmt)
    if rec is None:
        raise DomainError(RESULT_NOT_FOUND, f"No {fmt} export recorded for {result_id}", field="format")
    path, rel = export_path(store, result_id, fmt)
    if rel != rec["path"] or not path.is_file():
        raise DomainError(RESULT_NOT_FOUND, "Recorded export file is missing", field="format")
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    if h.hexdigest() != rec["sha256"]:
        raise DomainError(RESULT_NOT_FOUND, "Recorded export bytes do not match their SHA-256; regenerate the export", field="format")
    return path


__all__ = ["FORMATS", "MEDIA_TYPES", "build_export", "check_format", "check_result_id", "export_path", "verify_export_file", "canonical_dumps"]
