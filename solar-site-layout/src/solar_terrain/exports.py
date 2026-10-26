"""Write-once exports of an immutable placement (CONTRACTS.md section 8).

Files live under DATA_DIR/terrain-exports/<placement_id>/v1/ and are a pure function of
the stored placement row and records, so every process writes the same bytes:
* json: solar.terrain.placement.export/1, normalized request, summary and every record;
* csv: one row per module of a placed table (absolute corners in the terrain's vertical reference);
* supports_csv: one row per support of a placed or infeasible table.

Publication of one (placement, format) is serialized across threads (in-process lock) and
processes (flock). Each build stages into a unique temporary file beside the target, is
fsynced and atomically renamed, and only then recorded. An issued path keeps its SHA-256:
a reuse re-hashes the file (a damaged or tampered file is rebuilt with identical bytes),
and a rebuild with different bytes is refused.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
import threading
import weakref
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, Callable, Iterable, Iterator

from solar_layout.errors import INTERNAL_ERROR, INVALID_INPUT, PLACEMENT_NOT_FOUND, DomainError
from solar_layout.jsonio import canonical_dumps, fmt_float

from . import EXPORT_SCHEMA
from .store import TerrainStore, fault_point

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

PLACEMENT_ID_RE = re.compile(r"^plc_[0-9a-f]{24}$")
EXPORT_LAYOUT = "v1"
FORMATS = {"json": "placement.json", "csv": "modules.csv", "supports_csv": "supports.csv"}
MEDIA_TYPES = {"json": "application/json", "csv": "text/csv; charset=utf-8", "supports_csv": "text/csv; charset=utf-8"}
MODULE_COLUMNS = ["module_id", "table_id"] + [f"c{k}_{a}_m" for k in range(4) for a in ("x", "y", "z")]
SUPPORT_COLUMNS = ["support_id", "table_id", "a_m", "d_m", "x_m", "y_m", "ground_z_m", "top_z_m", "above_ground_m"]


def check_placement_id(placement_id: Any) -> str:
    if not isinstance(placement_id, str) or not PLACEMENT_ID_RE.match(placement_id):
        raise DomainError(PLACEMENT_NOT_FOUND, "Malformed placement ID; expected plc_ followed by 24 hex digits", field="placement_id")
    return placement_id


def check_format(fmt: Any) -> str:
    if not isinstance(fmt, str) or fmt not in FORMATS:
        raise DomainError(INVALID_INPUT, f"Unsupported placement export format {fmt!r}; use one of {sorted(FORMATS)}", field="format", details={"supported": sorted(FORMATS)})
    return fmt


def _inside_root(store: TerrainStore, rel: str) -> Path:
    path = (store.export_root / rel).resolve()
    if not path.is_relative_to(store.export_root):
        raise DomainError(INVALID_INPUT, "Export path escapes the managed export root", field="format")
    return path


def export_path(store: TerrainStore, placement_id: str, fmt: str) -> tuple[Path, str]:
    check_placement_id(placement_id)
    check_format(fmt)
    rel = f"{placement_id}/{EXPORT_LAYOUT}/{placement_id}-{FORMATS[fmt]}"
    return _inside_root(store, rel), rel


# ---- writers ---------------------------------------------------------------------------------


def write_json(out: IO[str], row: dict[str, Any], tables: Iterable[dict], modules: Iterable[dict], supports: Iterable[dict]) -> None:
    out.write("{\n")
    out.write(f'"schema_version": {json.dumps(EXPORT_SCHEMA)},\n')
    out.write(
        '"note": "x, y are metres in the layout and terrain frame (x East, y North); z values are elevations in the terrain\'s vertical reference (z_kind terrain_vertical_reference). '
        'Support heights are above-ground heights of the stated support points, not embedment depths or pile lengths.",\n'
    )
    out.write(f'"request": {canonical_dumps(row["request"])},\n')
    out.write(f'"result": {canonical_dumps(row["summary"])},\n')
    out.write(f'"export": {canonical_dumps({"layout": EXPORT_LAYOUT, "context": "result_only"})},\n')
    for name, records, last in (("tables", tables, False), ("modules", modules, False), ("supports", supports, True)):
        out.write(f'"{name}": [')
        first = True
        for rec in records:
            out.write(("\n" if first else ",\n") + canonical_dumps(rec))
            first = False
        out.write("\n]" + ("\n" if last else ",\n"))
    out.write("}\n")


def write_modules_csv(out: IO[str], modules: Iterable[dict]) -> None:
    w = csv.writer(out, lineterminator="\n")
    w.writerow(MODULE_COLUMNS)
    for m in modules:
        row = [m["module_id"], m["table_id"]]
        for x, y, z in m["corners_xyz_m"]:
            row += [fmt_float(x), fmt_float(y), fmt_float(z)]
        w.writerow(row)


def write_supports_csv(out: IO[str], supports: Iterable[dict]) -> None:
    w = csv.writer(out, lineterminator="\n")
    w.writerow(SUPPORT_COLUMNS)
    for s in supports:
        w.writerow([s["support_id"], s["table_id"], fmt_float(s["a_m"]), fmt_float(s["d_m"]), fmt_float(s["xy_m"][0]), fmt_float(s["xy_m"][1]), fmt_float(s["ground_z_m"]), fmt_float(s["top_z_m"]), fmt_float(s["above_ground_m"])])


# ---- locking, staging, publication -----------------------------------------------------------

_THREAD_LOCKS: "weakref.WeakValueDictionary[str, threading.Lock]" = weakref.WeakValueDictionary()
_THREAD_LOCKS_GUARD = threading.Lock()


@contextmanager
def _publication_lock(store: TerrainStore, placement_id: str, fmt: str) -> Iterator[None]:
    key = f"{store.export_root}\0{placement_id}\0{fmt}"
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = _THREAD_LOCKS[key] = threading.Lock()
    lock_dir = _inside_root(store, f"{placement_id}/{EXPORT_LAYOUT}")
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


def _write_staged(path: Path, writer: Callable[[IO[str]], None]) -> tuple[Path, str, int]:
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

            text = io.TextIOWrapper(io.BufferedWriter(_Tee(), buffer_size=1 << 16), encoding="utf-8", newline="")
            writer(text)
            text.flush()
            text.detach()
            fault_point("terrain_export:before_rename")
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp, h.hexdigest(), size


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:  # pragma: no cover
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


def _meta(placement_id: str, fmt: str, rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "placement_id": placement_id,
        "format": fmt,
        "path": rec["path"],
        "file_name": rec["path"].rsplit("/", 1)[1],
        "sha256": rec["sha256"],
        "bytes": rec["bytes"],
        "media_type": MEDIA_TYPES[fmt],
        "context": "result_only",
    }


def _build_unlocked(store: TerrainStore, placement_id: str, fmt: str) -> dict[str, Any]:
    path, rel = export_path(store, placement_id, fmt)
    issued = store.get_published_export(rel)
    if issued is not None and _file_sha256(path) == issued["sha256"]:
        return _meta(placement_id, fmt, issued)
    row = store.get_placement_row(placement_id)

    def recs(kind: str):
        return store.iter_records(placement_id, kind)

    if fmt == "json":
        writer = lambda f: write_json(f, row, recs("tables"), recs("modules"), recs("supports"))  # noqa: E731
    elif fmt == "csv":
        writer = lambda f: write_modules_csv(f, recs("modules"))  # noqa: E731
    else:
        writer = lambda f: write_supports_csv(f, recs("supports"))  # noqa: E731
    tmp, digest, size = _write_staged(path, writer)
    try:
        if issued is not None and issued["sha256"] != digest:
            raise DomainError(
                INTERNAL_ERROR,
                "Rebuilding an issued export gave different bytes; the issued record is kept and the rebuild discarded",
                field="format",
                details={"path": rel, "issued_sha256": issued["sha256"], "rebuilt_sha256": digest},
            )
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)
    return _meta(placement_id, fmt, store.publish_export(placement_id, fmt, rel, digest, size))


def build_export(store: TerrainStore, placement_id: str, fmt: str) -> dict[str, Any]:
    check_placement_id(placement_id)
    check_format(fmt)
    with _publication_lock(store, placement_id, fmt):
        return _build_unlocked(store, placement_id, fmt)


def open_export(store: TerrainStore, placement_id: str, fmt: str) -> tuple[IO[bytes], dict[str, Any]]:
    """Publish or reuse an export; return a handle on bytes hashed through that handle."""
    for _ in range(2):
        meta = build_export(store, placement_id, fmt)
        fh = open(_inside_root(store, meta["path"]), "rb")
        h = hashlib.sha256()
        while chunk := fh.read(1 << 20):
            h.update(chunk)
        if h.hexdigest() == meta["sha256"]:
            fh.seek(0)
            return fh, meta
        fh.close()
    raise DomainError(INTERNAL_ERROR, "The export file kept changing while it was being opened", field="format")
