"""SQLite persistence for terrains and placements: DATA_DIR/terrain.sqlite3.

Module 01's database (solar.sqlite3) is never opened here.

* Every write runs in one `BEGIN IMMEDIATE` transaction on a fresh connection (WAL), so
  separate processes serialize through SQLite's lock.
* A terrain (metadata row + its arrays) and a placement (summary row + every table,
  module and support record) are each inserted in ONE transaction. The parent row is
  written last, so an interruption at any fault point leaves no row and no partial records.
* Terrains and placements are immutable and content-addressed: inserting an existing ID is
  a no-op that keeps the stored row.
* Arrays are stored as little-endian binary with their SHA-256, which is re-checked on load.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np

from solar_layout.errors import INTERNAL_ERROR, PLACEMENT_NOT_FOUND, TERRAIN_NOT_FOUND, DomainError
from solar_layout.jsonio import canonical_dumps

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS terrains (
    terrain_id TEXT PRIMARY KEY,
    terrain_digest TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    name TEXT,
    source_json TEXT NOT NULL,
    frame_json TEXT NOT NULL,
    vertical_json TEXT NOT NULL,
    vertex_count INTEGER NOT NULL,
    triangle_count INTEGER NOT NULL,
    info_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS terrain_arrays (
    terrain_id TEXT NOT NULL,
    name TEXT NOT NULL,
    dtype TEXT NOT NULL,
    shape_json TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    data BLOB NOT NULL,
    PRIMARY KEY (terrain_id, name)
);
CREATE TABLE IF NOT EXISTS placements (
    placement_id TEXT PRIMARY KEY,
    payload_digest TEXT NOT NULL,
    terrain_id TEXT NOT NULL,
    source_result_id TEXT NOT NULL,
    source_payload_digest TEXT NOT NULL,
    request_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    table_count INTEGER NOT NULL,
    module_count INTEGER NOT NULL,
    support_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS placement_tables (
    placement_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    table_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (placement_id, seq)
);
CREATE TABLE IF NOT EXISTS placement_modules (
    placement_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    module_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (placement_id, seq)
);
CREATE TABLE IF NOT EXISTS placement_supports (
    placement_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    support_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (placement_id, seq)
);
-- One write-once row per issued export file; a published path keeps its SHA-256.
CREATE TABLE IF NOT EXISTS published_exports (
    relpath TEXT PRIMARY KEY,
    placement_id TEXT NOT NULL,
    format TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS published_exports_by_placement ON published_exports(placement_id, format, created_at);
"""

STORE_SCHEMA_VERSION = "solar.terrain.store/1"
KIND_TABLES = {"tables": "placement_tables", "modules": "placement_modules", "supports": "placement_supports"}
_ID_COLUMN = {"tables": "table_id", "modules": "module_id", "supports": "support_id"}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def fault_point(name: str) -> None:
    """Controlled interruption for tests: SOLAR_FAULT_POINT=<name>, SOLAR_FAULT_MODE=raise|kill."""
    if os.environ.get("SOLAR_FAULT_POINT") != name:
        return
    if os.environ.get("SOLAR_FAULT_MODE", "raise") == "kill":
        os.kill(os.getpid(), signal.SIGKILL)
    raise RuntimeError(f"injected fault at {name}")


def _array_blob(arr: np.ndarray) -> tuple[str, str, str, bytes]:
    a = np.ascontiguousarray(arr)
    dtype = a.dtype.newbyteorder("<").str
    data = a.astype(dtype, copy=False).tobytes()
    return dtype, json.dumps(list(a.shape)), hashlib.sha256(data).hexdigest(), data


class TerrainStore:
    def __init__(self, data_dir: str | os.PathLike):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "terrain.sqlite3"
        self.export_root = (self.data_dir / "terrain-exports").resolve()
        self.export_root.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)
            con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('store_schema', ?)", (STORE_SCHEMA_VERSION,))

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=FULL")
            con.execute("PRAGMA busy_timeout=30000")
            yield con
        finally:
            con.close()

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                yield con
            except BaseException:
                con.execute("ROLLBACK")
                raise
            else:
                con.execute("COMMIT")

    # ---- terrains -------------------------------------------------------------------------
    def terrain_exists(self, terrain_id: str) -> bool:
        with self.connect() as con:
            return con.execute("SELECT 1 FROM terrains WHERE terrain_id=?", (terrain_id,)).fetchone() is not None

    def insert_terrain(self, prepared: Any, provenance: dict[str, Any], schema_version: str, created_at: str) -> bool:
        """Store a prepared surface; returns False if the ID was already stored (kept as is)."""
        arrays = {"vertices": prepared.vertices, "triangles": prepared.triangles, "boundary_segments": prepared.boundary_segments}
        with self.write() as con:
            if con.execute("SELECT 1 FROM terrains WHERE terrain_id=?", (prepared.terrain_id,)).fetchone():
                return False
            for name, arr in arrays.items():
                dtype, shape, sha, data = _array_blob(arr)
                con.execute(
                    "INSERT INTO terrain_arrays(terrain_id, name, dtype, shape_json, sha256, data) VALUES (?,?,?,?,?,?)",
                    (prepared.terrain_id, name, dtype, shape, sha, data),
                )
                fault_point("terrain:arrays_partially_written")
            fault_point("terrain:before_row")
            con.execute(
                "INSERT INTO terrains(terrain_id, terrain_digest, schema_version, name, source_json, frame_json, vertical_json, vertex_count, triangle_count, info_json, provenance_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    prepared.terrain_id,
                    prepared.terrain_digest,
                    schema_version,
                    prepared.name,
                    canonical_dumps(prepared.source),
                    canonical_dumps(prepared.frame),
                    canonical_dumps(prepared.vertical),
                    int(len(prepared.vertices)),
                    int(len(prepared.triangles)),
                    canonical_dumps(prepared.info),
                    canonical_dumps(provenance),
                    created_at,
                ),
            )
            fault_point("terrain:before_commit")
        return True

    def get_terrain_row(self, terrain_id: str) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute(
                "SELECT terrain_id, terrain_digest, schema_version, name, source_json, frame_json, vertical_json, vertex_count, triangle_count, info_json, provenance_json, created_at FROM terrains WHERE terrain_id=?",
                (terrain_id,),
            ).fetchone()
        if row is None:
            raise DomainError(TERRAIN_NOT_FOUND, f"Terrain {terrain_id!r} does not exist", field="terrain_id")
        return {
            "terrain_id": row[0],
            "terrain_digest": row[1],
            "schema_version": row[2],
            "name": row[3],
            "source": json.loads(row[4]),
            "frame": json.loads(row[5]),
            "vertical": json.loads(row[6]),
            "vertex_count": row[7],
            "triangle_count": row[8],
            "info": json.loads(row[9]),
            "provenance": json.loads(row[10]),
            "created_at": row[11],
        }

    def load_arrays(self, terrain_id: str) -> dict[str, np.ndarray]:
        with self.connect() as con:
            rows = con.execute("SELECT name, dtype, shape_json, sha256, data FROM terrain_arrays WHERE terrain_id=?", (terrain_id,)).fetchall()
        if not rows:
            raise DomainError(TERRAIN_NOT_FOUND, f"Terrain {terrain_id!r} does not exist", field="terrain_id")
        out = {}
        for name, dtype, shape, sha, data in rows:
            if hashlib.sha256(data).hexdigest() != sha:
                raise DomainError(INTERNAL_ERROR, f"Stored terrain array {name!r} of {terrain_id} does not match its SHA-256", field="terrain_id")
            out[name] = np.frombuffer(data, dtype=np.dtype(dtype)).reshape(json.loads(shape))
        return out

    # ---- placements -----------------------------------------------------------------------
    def placement_exists(self, placement_id: str) -> bool:
        with self.connect() as con:
            return con.execute("SELECT 1 FROM placements WHERE placement_id=?", (placement_id,)).fetchone() is not None

    def insert_placement(
        self,
        placement_id: str,
        payload_digest: str,
        terrain_id: str,
        source_result_id: str,
        source_payload_digest: str,
        request: dict[str, Any],
        summary: dict[str, Any],
        tables: Iterable[dict[str, Any]],
        modules: Iterable[dict[str, Any]],
        supports: Iterable[dict[str, Any]],
        created_at: str,
    ) -> bool:
        counts = {"tables": 0, "modules": 0, "supports": 0}
        with self.write() as con:
            if con.execute("SELECT 1 FROM placements WHERE placement_id=?", (placement_id,)).fetchone():
                return False
            for kind, records in (("tables", tables), ("modules", modules), ("supports", supports)):
                sql = f"INSERT INTO {KIND_TABLES[kind]}(placement_id, seq, {_ID_COLUMN[kind]}, record_json) VALUES (?,?,?,?)"
                batch: list[tuple] = []
                for rec in records:
                    batch.append((placement_id, rec["seq"], rec[_ID_COLUMN[kind]], canonical_dumps(rec)))
                    if len(batch) >= 2000:
                        con.executemany(sql, batch)
                        counts[kind] += len(batch)
                        batch = []
                        fault_point("placement:records_partially_written")
                if batch:
                    con.executemany(sql, batch)
                    counts[kind] += len(batch)
            fault_point("placement:before_row")
            con.execute(
                "INSERT INTO placements(placement_id, payload_digest, terrain_id, source_result_id, source_payload_digest, request_json, summary_json, table_count, module_count, support_count, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    placement_id,
                    payload_digest,
                    terrain_id,
                    source_result_id,
                    source_payload_digest,
                    canonical_dumps(request),
                    canonical_dumps(summary),
                    counts["tables"],
                    counts["modules"],
                    counts["supports"],
                    created_at,
                ),
            )
            fault_point("placement:before_commit")
        return True

    def get_placement_row(self, placement_id: str) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute(
                "SELECT placement_id, payload_digest, terrain_id, source_result_id, source_payload_digest, request_json, summary_json, table_count, module_count, support_count, created_at FROM placements WHERE placement_id=?",
                (placement_id,),
            ).fetchone()
            if row is None:
                raise DomainError(PLACEMENT_NOT_FOUND, f"Placement {placement_id!r} does not exist", field="placement_id")
            exports = con.execute(
                "SELECT format, relpath, sha256, bytes, created_at FROM published_exports WHERE placement_id=? ORDER BY format, created_at, relpath",
                (placement_id,),
            ).fetchall()
        return {
            "placement_id": row[0],
            "payload_digest": row[1],
            "terrain_id": row[2],
            "source_result_id": row[3],
            "source_payload_digest": row[4],
            "request": json.loads(row[5]),
            "summary": json.loads(row[6]),
            "table_count": row[7],
            "module_count": row[8],
            "support_count": row[9],
            "created_at": row[10],
            "exports": [{"format": e[0], "path": e[1], "sha256": e[2], "bytes": e[3], "created_at": e[4]} for e in exports],
        }

    def page(self, placement_id: str, kind: str, start_seq: int, limit: int) -> list[dict[str, Any]]:
        table = KIND_TABLES[kind]
        with self.connect() as con:
            rows = con.execute(
                f"SELECT record_json FROM {table} WHERE placement_id=? AND seq>=? ORDER BY seq LIMIT ?",
                (placement_id, start_seq, limit),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def iter_records(self, placement_id: str, kind: str, chunk: int = 2000) -> Iterator[dict[str, Any]]:
        seq = 0
        while True:
            page = self.page(placement_id, kind, seq, chunk)
            if not page:
                return
            yield from page
            seq = page[-1]["seq"] + 1

    # ---- exports --------------------------------------------------------------------------
    def publish_export(self, placement_id: str, fmt: str, relpath: str, sha256: str, size: int) -> dict[str, Any]:
        """Write-once: re-publishing a path with the same SHA-256 is a no-op; a different
        SHA-256 for an issued path is refused."""
        with self.write() as con:
            row = con.execute("SELECT sha256, bytes, created_at FROM published_exports WHERE relpath=?", (relpath,)).fetchone()
            if row is None:
                ts = now()
                con.execute(
                    "INSERT INTO published_exports(relpath, placement_id, format, sha256, bytes, created_at) VALUES (?,?,?,?,?,?)",
                    (relpath, placement_id, fmt, sha256, size, ts),
                )
                return {"format": fmt, "path": relpath, "sha256": sha256, "bytes": size, "created_at": ts}
        if row[0] != sha256:
            raise DomainError(
                INTERNAL_ERROR,
                "An issued export would change its bytes; the issued file and record are kept",
                field="format",
                details={"path": relpath, "issued_sha256": row[0], "new_sha256": sha256},
            )
        return {"format": fmt, "path": relpath, "sha256": row[0], "bytes": row[1], "created_at": row[2]}

    def get_published_export(self, relpath: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT format, sha256, bytes, created_at FROM published_exports WHERE relpath=?", (relpath,)).fetchone()
        if row is None:
            return None
        return {"format": row[0], "path": relpath, "sha256": row[1], "bytes": row[2], "created_at": row[3]}
