"""Export orchestration: one immutable result -> write-once files in the managed export root.

Result exports (json, csv, svg, dxf, report, bundle) are derived from the immutable result
alone, so their bytes are a pure function of it. They live at a versioned path
(`<result_id>/v2/...`) and are published once: a later request reuses the issued file
after re-hashing it, and a rebuild that would give an issued path different bytes is
refused rather than written. Project associations change as projects reuse a result, so
they are exported separately as a content-addressed `context` file; every distinct
context gets its own path, and earlier context files are kept.

Publication of one (result, format) is serialized by a lock that holds across threads
(an in-process lock) and processes (an advisory `flock` on a lock file). Each build
stages into its own unique temporary file in the final directory, is flushed and
fsynced, and is then atomically renamed; only after that is it recorded in the store.
A crash at any point leaves either no file or an unreferenced `*.partial` file, never a
recorded export pointing at incomplete bytes. Paths are built only from a validated
result ID, an allow-listed format and (for context files) a SHA-256, and are checked to
stay inside the export root.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import threading
import weakref
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, Callable, Iterator

from ..errors import INTERNAL_ERROR, INVALID_INPUT, RESULT_NOT_FOUND, DomainError
from ..jsonio import canonical_dumps
from ..store import Store, fault_point
from .csvx import write_csv
from .dxf import build_dxf
from .jsonx import write_json
from .report import write_report
from .svg import write_svg

try:  # POSIX advisory locks; elsewhere only the in-process lock applies
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

RESULT_ID_RE = re.compile(r"^res_[0-9a-f]{24}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Path segment of the current export layout. v1 files (which embedded mutable project
# sources) are never rewritten; v2 starts a separate tree beside them.
EXPORT_LAYOUT = "v2"
RESULT_FORMATS = {
    "json": "layout.json",
    "csv": "modules.csv",
    "svg": "plan.svg",
    "dxf": "plan.dxf",
    "report": "report.md",
    "bundle": "bundle.zip",
}
FORMATS = {**RESULT_FORMATS, "context": "context.json"}
MEDIA_TYPES = {
    "json": "application/json",
    "csv": "text/csv; charset=utf-8",
    "svg": "image/svg+xml",
    "dxf": "application/dxf",
    "report": "text/markdown; charset=utf-8",
    "bundle": "application/zip",
    "context": "application/json",
}
CONTEXT_SCHEMA = "solar.layout.export-context/1"
BUNDLE_SCHEMA = "solar.layout.export-bundle/2"
BUNDLE_PARTS = ("json", "csv", "svg", "dxf", "report")
_ZIP_DATE = (2026, 1, 1, 0, 0, 0)


def check_result_id(result_id: Any) -> str:
    if not isinstance(result_id, str) or not RESULT_ID_RE.match(result_id):
        raise DomainError(RESULT_NOT_FOUND, "Malformed result ID; expected res_ followed by 24 hex digits", field="result_id")
    return result_id


def check_format(fmt: Any) -> str:
    if not isinstance(fmt, str) or fmt not in FORMATS:
        raise DomainError(INVALID_INPUT, f"Unsupported export format {fmt!r}; use one of {sorted(FORMATS)}", field="format", details={"supported": sorted(FORMATS)})
    return fmt


def _inside_root(store: Store, rel: str) -> Path:
    path = (store.export_root / rel).resolve()
    if not path.is_relative_to(store.export_root):
        raise DomainError(INVALID_INPUT, "Export path escapes the managed export root", field="format")
    return path


def export_path(store: Store, result_id: str, fmt: str, content_sha256: str | None = None) -> tuple[Path, str]:
    check_result_id(result_id)
    check_format(fmt)
    if fmt == "context":
        if not isinstance(content_sha256, str) or not SHA256_RE.match(content_sha256):
            raise DomainError(INVALID_INPUT, "A context export path needs the SHA-256 of its content", field="format")
        rel = f"{result_id}/{EXPORT_LAYOUT}/context/{result_id}-context-{content_sha256[:16]}.json"
    else:
        rel = f"{result_id}/{EXPORT_LAYOUT}/{result_id}-{FORMATS[fmt]}"
    return _inside_root(store, rel), rel


# ---- locking ---------------------------------------------------------------------------

# One lock per (export root, result, format), dropped when no thread holds it. Locks are
# only ever nested bundle -> part, so there is no lock-order cycle.
_THREAD_LOCKS: "weakref.WeakValueDictionary[str, threading.Lock]" = weakref.WeakValueDictionary()
_THREAD_LOCKS_GUARD = threading.Lock()


@contextmanager
def _publication_lock(store: Store, result_id: str, fmt: str) -> Iterator[None]:
    """Serialize publication of one (result, format) across threads and processes."""
    key = f"{store.export_root}\0{result_id}\0{fmt}"
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = _THREAD_LOCKS[key] = threading.Lock()
    lock_dir = _inside_root(store, f"{result_id}/{EXPORT_LAYOUT}")
    with lock:
        if fcntl is None:  # pragma: no cover - non-POSIX
            yield
            return
        lock_dir.mkdir(parents=True, exist_ok=True)
        with open(lock_dir / f".{fmt}.lock", "a+b") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


# ---- staging and publication -----------------------------------------------------------


def _write_staged(path: Path, writer: Callable[[Any], None], binary: bool) -> tuple[Path, str, int]:
    """Write to a unique temporary file beside `path`; return (temp path, sha256, size).
    The temporary file is fsynced but not yet published."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".partial")
    tmp = Path(name)
    h = hashlib.sha256()
    size = 0
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as fh:

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
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp, h.hexdigest(), size


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:  # pragma: no cover - platforms without directory handles
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _file_sha256(path: Path) -> str | None:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 20):
                h.update(chunk)
    except FileNotFoundError:
        return None
    return h.hexdigest()


def _meta(result_id: str, fmt: str, rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "result_id": result_id,
        "format": fmt,
        "path": rec["path"],
        "file_name": rec["path"].rsplit("/", 1)[1],
        "sha256": rec["sha256"],
        "bytes": rec["bytes"],
        "media_type": MEDIA_TYPES[fmt],
        "context": "project_associations" if fmt == "context" else "result_only",
    }


def _publish(store: Store, result_id: str, fmt: str, path: Path, rel: str, writer: Callable[[Any], None], binary: bool) -> dict[str, Any]:
    tmp, digest, size = _write_staged(path, writer, binary)
    try:
        issued = store.get_published_export(rel)
        if issued is not None and issued["sha256"] != digest:
            raise DomainError(
                INTERNAL_ERROR,
                "Rebuilding an issued export gave different bytes; the issued export is kept and the rebuild discarded",
                field="format",
                details={"path": rel, "issued_sha256": issued["sha256"], "rebuilt_sha256": digest},
            )
        # Every writer of this path produces these same bytes, so the rename is safe even
        # if another (unlocked) writer published a moment earlier.
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)
    return _meta(result_id, fmt, store.publish_export(result_id, fmt, rel, digest, size))


def _reusable(store: Store, result_id: str, fmt: str, path: Path, rel: str) -> dict[str, Any] | None:
    """The issued export at `rel`, if its file still hashes to the recorded SHA-256."""
    issued = store.get_published_export(rel)
    if issued is not None and _file_sha256(path) == issued["sha256"]:
        return _meta(result_id, fmt, issued)
    return None


def _context_bytes(row: dict[str, Any]) -> bytes:
    doc = {
        "schema_version": CONTEXT_SCHEMA,
        "note": (
            "Project associations of an immutable result at the time of this export. They change "
            "when other projects or revisions reuse the result, so they are never written into the "
            "result exports (json, csv, svg, dxf, report, bundle); each distinct context is a new file."
        ),
        "result_id": row["result_id"],
        "input_digest": row["input_digest"],
        "payload_digest": row["payload_digest"],
        "result_export_layout": EXPORT_LAYOUT,
        "project_sources": [
            {"project_id": s["project_id"], "project_revision": s["project_revision"], "interface": s["interface"], "created_at": s["created_at"]}
            for s in row["sources"]
        ],
    }
    return (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode()


def _build_unlocked(store: Store, result_id: str, fmt: str, row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Publish (or reuse) one export. Callers hold the publication lock; tests call this
    directly to force overlapping writers."""
    if row is None:
        row = store.get_result_row(result_id)
    if fmt == "context":
        data = _context_bytes(row)
        path, rel = export_path(store, result_id, fmt, hashlib.sha256(data).hexdigest())
        return _reusable(store, result_id, fmt, path, rel) or _publish(store, result_id, fmt, path, rel, lambda f: f.write(data), True)

    path, rel = export_path(store, result_id, fmt)
    issued = _reusable(store, result_id, fmt, path, rel)
    if issued is not None:
        return issued
    request = row["request"]
    summary = row["summary"]
    provenance = row["provenance"]
    regions = store.get_regions(result_id)

    def tables():
        return store.iter_records(result_id, "tables")

    def modules():
        return store.iter_records(result_id, "modules")

    if fmt == "json":
        return _publish(store, result_id, fmt, path, rel, lambda f: write_json(f, request, summary, provenance, regions, tables(), modules(), EXPORT_LAYOUT), False)
    if fmt == "csv":
        return _publish(store, result_id, fmt, path, rel, lambda f: write_csv(f, modules()), False)
    if fmt == "svg":
        return _publish(store, result_id, fmt, path, rel, lambda f: write_svg(f, request, summary, regions, tables(), modules()), False)
    if fmt == "report":
        return _publish(store, result_id, fmt, path, rel, lambda f: write_report(f, request, summary, provenance), False)
    if fmt == "dxf":
        doc = build_dxf(request, summary, regions, tables(), modules())
        return _publish(store, result_id, fmt, path, rel, lambda f: _write_dxf(doc, f), True)

    # bundle: every part comes from the same row snapshot, and each part's bytes are
    # re-hashed as they are copied, so the manifest describes exactly what is zipped.
    parts = {sub: build_export(store, result_id, sub, row=row) for sub in BUNDLE_PARTS}
    manifest = {
        "schema_version": BUNDLE_SCHEMA,
        "export_layout": EXPORT_LAYOUT,
        "context": "result_only",
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
        "files": [{"name": FORMATS[sub], "format": sub, "sha256": parts[sub]["sha256"], "bytes": parts[sub]["bytes"]} for sub in parts],
    }

    def write_zip(f):
        with zipfile.ZipFile(f, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for sub, meta in parts.items():
                info = zipfile.ZipInfo(FORMATS[sub], date_time=_ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                h = hashlib.sha256()
                with open(_inside_root(store, meta["path"]), "rb") as src, z.open(info, "w") as dst:
                    while chunk := src.read(1 << 20):
                        h.update(chunk)
                        dst.write(chunk)
                if h.hexdigest() != meta["sha256"]:
                    raise DomainError(INTERNAL_ERROR, f"The {sub} export changed while it was being bundled", field="format")
            info = zipfile.ZipInfo("manifest.json", date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, json.dumps(manifest, indent=1, sort_keys=True))

    return _publish(store, result_id, fmt, path, rel, write_zip, True)


def build_export(store: Store, result_id: str, fmt: str, row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Publish one export of a stored result, or return the already issued one."""
    check_result_id(result_id)
    check_format(fmt)
    with _publication_lock(store, result_id, fmt):
        return _build_unlocked(store, result_id, fmt, row)


def open_export(store: Store, result_id: str, fmt: str) -> tuple[IO[bytes], dict[str, Any]]:
    """Publish or reuse an export and return an open handle positioned at the start of
    bytes that were hashed through that same handle, with their metadata. Exports are
    replaced only by rename, so the handle's bytes cannot change while they are served."""
    for _ in range(2):
        meta = build_export(store, result_id, fmt)
        fh = open(_inside_root(store, meta["path"]), "rb")
        h = hashlib.sha256()
        while chunk := fh.read(1 << 20):
            h.update(chunk)
        if h.hexdigest() == meta["sha256"]:
            fh.seek(0)
            return fh, meta
        fh.close()  # altered after publication: the next build_export restores it
    raise DomainError(INTERNAL_ERROR, "The export file kept changing while it was being opened", field="format")


def _write_dxf(doc, raw) -> None:
    text = io.TextIOWrapper(io.BufferedWriter(raw, buffer_size=1 << 16), encoding="utf-8", newline="")
    doc.write(text)
    text.flush()
    text.detach()


def verify_export_file(store: Store, result_id: str, fmt: str) -> Path:
    """Return the file path of the latest issued export after checking its bytes still match."""
    check_result_id(result_id)
    check_format(fmt)
    rec = store.get_export(result_id, fmt)
    if rec is None:
        raise DomainError(RESULT_NOT_FOUND, f"No {fmt} export recorded for {result_id}", field="format")
    path = _inside_root(store, rec["path"])
    if _file_sha256(path) != rec["sha256"]:
        raise DomainError(RESULT_NOT_FOUND, "Recorded export file is missing or does not match its SHA-256; regenerate the export", field="format")
    return path


__all__ = [
    "EXPORT_LAYOUT",
    "FORMATS",
    "MEDIA_TYPES",
    "RESULT_FORMATS",
    "build_export",
    "canonical_dumps",
    "check_format",
    "check_result_id",
    "export_path",
    "open_export",
    "verify_export_file",
]
