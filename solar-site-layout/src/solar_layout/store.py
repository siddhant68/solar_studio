"""SQLite persistence: editable projects with integer revisions, immutable results.

* Every write runs in its own `BEGIN IMMEDIATE` transaction on a fresh connection, so
  separate processes serialize through SQLite's lock (WAL mode), not an in-process lock.
* Project updates are compare-and-swap on the expected revision.
* A result (summary + every table and module row) is inserted in ONE transaction:
  a crash or injected fault before COMMIT leaves no result row and no partial records.
* Table/module records are stored one row each, keyed by (result_id, seq), so a page read
  is an indexed range query and a summary read never touches coordinates.
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from .errors import PROJECT_NOT_FOUND, RESULT_NOT_FOUND, REVISION_CONFLICT, DomainError
from .jsonio import canonical_dumps

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    revision INTEGER NOT NULL,
    request_json TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    selected_result_id TEXT,
    selected_result_revision INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_revisions (
    project_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    name TEXT NOT NULL,
    request_json TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_id, revision)
);
CREATE TABLE IF NOT EXISTS results (
    result_id TEXT PRIMARY KEY,
    input_digest TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    request_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    regions_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    verification_json TEXT NOT NULL,
    table_count INTEGER NOT NULL,
    module_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS result_sources (
    result_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    project_revision INTEGER NOT NULL,
    interface TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (result_id, project_id, project_revision)
);
CREATE TABLE IF NOT EXISTS layout_tables (
    result_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    table_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (result_id, seq)
);
CREATE TABLE IF NOT EXISTS layout_modules (
    result_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    module_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (result_id, seq)
);
CREATE TABLE IF NOT EXISTS exports (
    result_id TEXT NOT NULL,
    format TEXT NOT NULL,
    relpath TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (result_id, format)
);
"""

STORE_SCHEMA_VERSION = "solar.store/1"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def fault_point(name: str) -> None:
    """Controlled interruption for tests: SOLAR_FAULT_POINT=<name>, SOLAR_FAULT_MODE=raise|kill."""
    if os.environ.get("SOLAR_FAULT_POINT") != name:
        return
    if os.environ.get("SOLAR_FAULT_MODE", "raise") == "kill":
        os.kill(os.getpid(), signal.SIGKILL)
    raise RuntimeError(f"injected fault at {name}")


class Store:
    def __init__(self, data_dir: str | os.PathLike):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "solar.sqlite3"
        self.export_root = (self.data_dir / "exports").resolve()
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

    # ---- projects ---------------------------------------------------------------------
    def create_project(self, name: str, request: dict[str, Any], input_digest: str) -> dict[str, Any]:
        pid = "prj_" + uuid.uuid4().hex[:20]
        ts = now()
        body = canonical_dumps(request)
        with self.write() as con:
            con.execute(
                "INSERT INTO projects(project_id, name, revision, request_json, input_digest, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (pid, name, 1, body, input_digest, ts, ts),
            )
            con.execute(
                "INSERT INTO project_revisions(project_id, revision, name, request_json, input_digest, created_at) VALUES (?,?,?,?,?,?)",
                (pid, 1, name, body, input_digest, ts),
            )
        return self.get_project(pid)

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute(
                "SELECT project_id, name, revision, request_json, input_digest, selected_result_id, selected_result_revision, created_at, updated_at FROM projects WHERE project_id=?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise DomainError(PROJECT_NOT_FOUND, f"Project {project_id!r} does not exist", field="project_id")
        return {
            "project_id": row[0],
            "name": row[1],
            "revision": row[2],
            "request": json.loads(row[3]),
            "input_digest": row[4],
            "selected_result_id": row[5],
            "selected_result_revision": row[6],
            "selected_result_is_current": row[5] is not None and row[6] == row[2],
            "created_at": row[7],
            "updated_at": row[8],
        }

    def get_project_revision(self, project_id: str, revision: int) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute(
                "SELECT name, request_json, input_digest, created_at FROM project_revisions WHERE project_id=? AND revision=?",
                (project_id, revision),
            ).fetchone()
        if row is None:
            self.get_project(project_id)  # raises PROJECT_NOT_FOUND if the project is missing
            raise DomainError(PROJECT_NOT_FOUND, f"Project {project_id!r} has no revision {revision}", field="revision")
        return {"project_id": project_id, "revision": revision, "name": row[0], "request": json.loads(row[1]), "input_digest": row[2], "created_at": row[3]}

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute("SELECT project_id, name, revision, updated_at FROM projects ORDER BY updated_at DESC").fetchall()
        return [{"project_id": r[0], "name": r[1], "revision": r[2], "updated_at": r[3]} for r in rows]

    def update_project(self, project_id: str, expected_revision: int, name: str, request: dict[str, Any], input_digest: str) -> dict[str, Any]:
        ts = now()
        body = canonical_dumps(request)
        with self.write() as con:
            row = con.execute("SELECT revision FROM projects WHERE project_id=?", (project_id,)).fetchone()
            if row is None:
                raise DomainError(PROJECT_NOT_FOUND, f"Project {project_id!r} does not exist", field="project_id")
            cur = con.execute(
                "UPDATE projects SET revision=revision+1, name=?, request_json=?, input_digest=?, updated_at=? WHERE project_id=? AND revision=?",
                (name, body, input_digest, ts, project_id, expected_revision),
            )
            if cur.rowcount != 1:
                raise DomainError(
                    REVISION_CONFLICT,
                    f"Project {project_id} is at revision {row[0]}, not the expected revision {expected_revision}; reload before saving",
                    field="expected_revision",
                    details={"current_revision": row[0], "expected_revision": expected_revision},
                )
            con.execute(
                "INSERT INTO project_revisions(project_id, revision, name, request_json, input_digest, created_at) VALUES (?,?,?,?,?,?)",
                (project_id, expected_revision + 1, name, body, input_digest, ts),
            )
        return self.get_project(project_id)

    def select_result_if_current(self, project_id: str, revision: int, result_id: str) -> bool:
        """Bind a result to its source revision as the project's selection, only if that
        revision is still the project's current revision (compare-and-swap)."""
        with self.write() as con:
            cur = con.execute(
                "UPDATE projects SET selected_result_id=?, selected_result_revision=? WHERE project_id=? AND revision=?",
                (result_id, revision, project_id, revision),
            )
            return cur.rowcount == 1

    # ---- results ----------------------------------------------------------------------
    def result_exists(self, result_id: str) -> bool:
        with self.connect() as con:
            return con.execute("SELECT 1 FROM results WHERE result_id=?", (result_id,)).fetchone() is not None

    def insert_result(
        self,
        result_id: str,
        input_digest: str,
        payload_digest: str,
        request: dict[str, Any],
        summary: dict[str, Any],
        regions: dict[str, Any],
        provenance: dict[str, Any],
        verification: dict[str, Any],
        tables: Iterable[dict[str, Any]],
        modules: Iterable[dict[str, Any]],
        created_at: str,
    ) -> None:
        with self.write() as con:
            if con.execute("SELECT 1 FROM results WHERE result_id=?", (result_id,)).fetchone():
                return  # immutable and content-addressed: an identical result already exists
            con.executemany(
                "INSERT INTO layout_tables(result_id, seq, table_id, record_json) VALUES (?,?,?,?)",
                ((result_id, t["seq"], t["table_id"], canonical_dumps(t)) for t in tables),
            )
            batch: list[tuple] = []
            written = 0
            for m in modules:
                batch.append((result_id, m["seq"], m["module_id"], canonical_dumps(m)))
                if len(batch) >= 2000:
                    con.executemany("INSERT INTO layout_modules(result_id, seq, module_id, record_json) VALUES (?,?,?,?)", batch)
                    written += len(batch)
                    batch = []
                    fault_point("generate:modules_partially_written")
            if batch:
                con.executemany("INSERT INTO layout_modules(result_id, seq, module_id, record_json) VALUES (?,?,?,?)", batch)
                written += len(batch)
            fault_point("generate:before_result_row")
            con.execute(
                "INSERT INTO results(result_id, input_digest, payload_digest, request_json, summary_json, regions_json, provenance_json, verification_json, table_count, module_count, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    result_id,
                    input_digest,
                    payload_digest,
                    canonical_dumps(request),
                    canonical_dumps(summary),
                    canonical_dumps(regions),
                    canonical_dumps(provenance),
                    canonical_dumps(verification),
                    summary["quantities"]["table_count"],
                    summary["quantities"]["module_count"],
                    created_at,
                ),
            )
            fault_point("generate:before_commit")

    def add_result_source(self, result_id: str, project_id: str, revision: int, interface: str) -> None:
        with self.write() as con:
            con.execute(
                "INSERT OR IGNORE INTO result_sources(result_id, project_id, project_revision, interface, created_at) VALUES (?,?,?,?,?)",
                (result_id, project_id, revision, interface, now()),
            )

    def get_result_row(self, result_id: str) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute(
                "SELECT result_id, input_digest, payload_digest, request_json, summary_json, provenance_json, verification_json, table_count, module_count, created_at FROM results WHERE result_id=?",
                (result_id,),
            ).fetchone()
            if row is None:
                raise DomainError(RESULT_NOT_FOUND, f"Result {result_id!r} does not exist", field="result_id")
            sources = con.execute(
                "SELECT project_id, project_revision, interface, created_at FROM result_sources WHERE result_id=? ORDER BY created_at",
                (result_id,),
            ).fetchall()
            exports = con.execute("SELECT format, relpath, sha256, bytes, created_at FROM exports WHERE result_id=? ORDER BY format", (result_id,)).fetchall()
        return {
            "result_id": row[0],
            "input_digest": row[1],
            "payload_digest": row[2],
            "request": json.loads(row[3]),
            "summary": json.loads(row[4]),
            "provenance": json.loads(row[5]),
            "verification": json.loads(row[6]),
            "table_count": row[7],
            "module_count": row[8],
            "created_at": row[9],
            "sources": [{"project_id": s[0], "project_revision": s[1], "interface": s[2], "created_at": s[3]} for s in sources],
            "exports": [{"format": e[0], "path": e[1], "sha256": e[2], "bytes": e[3], "created_at": e[4]} for e in exports],
        }

    def get_regions(self, result_id: str) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute("SELECT regions_json FROM results WHERE result_id=?", (result_id,)).fetchone()
        if row is None:
            raise DomainError(RESULT_NOT_FOUND, f"Result {result_id!r} does not exist", field="result_id")
        return json.loads(row[0])

    def page(self, result_id: str, kind: str, start_seq: int, limit: int) -> list[dict[str, Any]]:
        table = "layout_tables" if kind == "tables" else "layout_modules"
        with self.connect() as con:
            rows = con.execute(
                f"SELECT record_json FROM {table} WHERE result_id=? AND seq>=? ORDER BY seq LIMIT ?",
                (result_id, start_seq, limit),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def iter_records(self, result_id: str, kind: str, chunk: int = 2000) -> Iterator[dict[str, Any]]:
        seq = 0
        while True:
            page = self.page(result_id, kind, seq, chunk)
            if not page:
                return
            yield from page
            seq = page[-1]["seq"] + 1

    def record_export(self, result_id: str, fmt: str, relpath: str, sha256: str, size: int) -> None:
        with self.write() as con:
            con.execute(
                "INSERT OR REPLACE INTO exports(result_id, format, relpath, sha256, bytes, created_at) VALUES (?,?,?,?,?,?)",
                (result_id, fmt, relpath, sha256, size, now()),
            )

    def get_export(self, result_id: str, fmt: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT relpath, sha256, bytes, created_at FROM exports WHERE result_id=? AND format=?", (result_id, fmt)).fetchone()
        if row is None:
            return None
        return {"format": fmt, "path": row[0], "sha256": row[1], "bytes": row[2], "created_at": row[3]}
