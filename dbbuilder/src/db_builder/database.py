"""SQLite database manager for DB Builder state tracking.

Manages file ingestion history, chunk metadata, checkpoints,
and build reports in a single SQLite database.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator


SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path       TEXT NOT NULL UNIQUE,
    file_hash       TEXT NOT NULL,
    file_size       INTEGER NOT NULL,
    source_type     TEXT NOT NULL,
    detected_mode   TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    error_message   TEXT,
    chunk_count     INTEGER DEFAULT 0,
    avg_quality     REAL,
    first_seen_at   TEXT NOT NULL,
    last_built_at   TEXT,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id                  TEXT PRIMARY KEY,
    file_id             INTEGER NOT NULL REFERENCES files(id),
    text                TEXT NOT NULL,
    token_count         INTEGER NOT NULL,

    chunk_type          TEXT NOT NULL,
    source_file         TEXT NOT NULL,
    source_type         TEXT NOT NULL,
    page_number         INTEGER,
    sheet_name          TEXT,
    tool_family         TEXT NOT NULL DEFAULT 'general',
    customer            TEXT NOT NULL DEFAULT 'generic',
    silo_key            TEXT NOT NULL DEFAULT '',
    section_path        TEXT,
    section_title       TEXT,
    document_version    TEXT,
    language            TEXT NOT NULL DEFAULT 'en',
    is_safety_critical  INTEGER NOT NULL DEFAULT 0,
    cross_references    TEXT,
    issue_thread_id     TEXT,
    source_date         TEXT,

    quality_score       REAL,
    quality_detail      TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    quarantine_reason   TEXT,

    is_embedded         INTEGER NOT NULL DEFAULT 0,
    embedded_at         TEXT,

    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              TEXT NOT NULL,
    job_type            TEXT NOT NULL,
    total_chunks        INTEGER NOT NULL,
    completed_chunks    INTEGER NOT NULL DEFAULT 0,
    last_batch_index    INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'running',
    started_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    completed_at        TEXT,
    error_message       TEXT
);

CREATE TABLE IF NOT EXISTS checkpoint_failures (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_id       INTEGER NOT NULL REFERENCES checkpoints(id),
    chunk_id            TEXT NOT NULL,
    error_message       TEXT,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS build_reports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              TEXT NOT NULL,
    total_files         INTEGER NOT NULL,
    total_chunks        INTEGER NOT NULL,
    accepted_chunks     INTEGER NOT NULL,
    quarantined_chunks  INTEGER NOT NULL,
    avg_quality         REAL NOT NULL,
    quality_distribution TEXT,
    source_type_breakdown TEXT,
    tool_family_breakdown TEXT,
    embedding_cost_usd  REAL,
    duration_seconds    REAL,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id);
CREATE INDEX IF NOT EXISTS idx_chunks_status ON chunks(status);
CREATE INDEX IF NOT EXISTS idx_chunks_quality ON chunks(quality_score);
CREATE INDEX IF NOT EXISTS idx_chunks_tool_family ON chunks(tool_family);
CREATE INDEX IF NOT EXISTS idx_chunks_is_embedded ON chunks(is_embedded);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_checkpoints_job_id ON checkpoints(job_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DatabaseManager:
    """SQLite database manager for DB Builder state."""

    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def init_schema(self) -> None:
        """Create all tables if they don't exist."""
        self.conn.executescript(_SCHEMA_SQL)
        # Set schema version if not present
        row = self.conn.execute("SELECT COUNT(*) FROM _schema_version").fetchone()
        if row[0] == 0:
            self.conn.execute(
                "INSERT INTO _schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        self.conn.commit()

    def get_schema_version(self) -> int:
        row = self.conn.execute("SELECT version FROM _schema_version").fetchone()
        return row["version"] if row else 0

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for atomic transactions."""
        cursor = self.conn.cursor()
        try:
            yield cursor
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── File operations ──

    def insert_file(
        self,
        file_path: str,
        file_hash: str,
        file_size: int,
        source_type: str,
        detected_mode: str | None = None,
    ) -> int:
        """Insert a new file record. Returns the file id."""
        now = _now()
        with self.transaction() as cur:
            cur.execute(
                """INSERT INTO files
                   (file_path, file_hash, file_size, source_type, detected_mode,
                    status, first_seen_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (file_path, file_hash, file_size, source_type, detected_mode, now, now),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_file_by_path(self, file_path: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM files WHERE file_path = ?", (file_path,)
        ).fetchone()
        return dict(row) if row else None

    def get_file_by_id(self, file_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_file_status(
        self,
        file_id: int,
        status: str,
        error_message: str | None = None,
        chunk_count: int | None = None,
        avg_quality: float | None = None,
    ) -> None:
        now = _now()
        fields = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, now]

        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        if chunk_count is not None:
            fields.append("chunk_count = ?")
            values.append(chunk_count)
        if avg_quality is not None:
            fields.append("avg_quality = ?")
            values.append(avg_quality)
        if status == "completed":
            fields.append("last_built_at = ?")
            values.append(now)

        values.append(file_id)
        with self.transaction() as cur:
            cur.execute(
                f"UPDATE files SET {', '.join(fields)} WHERE id = ?",
                values,
            )

    def update_file_hash(self, file_id: int, file_hash: str, file_size: int) -> None:
        with self.transaction() as cur:
            cur.execute(
                "UPDATE files SET file_hash = ?, file_size = ?, updated_at = ? WHERE id = ?",
                (file_hash, file_size, _now(), file_id),
            )

    def list_files(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM files WHERE status = ? ORDER BY file_path", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM files ORDER BY file_path"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Chunk operations ──

    def insert_chunk(self, chunk_data: dict[str, Any]) -> str:
        """Insert a chunk. chunk_data must include 'id' key. Returns chunk id."""
        now = _now()
        chunk_data.setdefault("created_at", now)
        chunk_data.setdefault("updated_at", now)
        chunk_data.setdefault("status", "pending")
        chunk_data.setdefault("is_embedded", 0)

        columns = list(chunk_data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)

        with self.transaction() as cur:
            cur.execute(
                f"INSERT OR REPLACE INTO chunks ({col_names}) VALUES ({placeholders})",
                list(chunk_data.values()),
            )
        return chunk_data["id"]

    def get_chunk_by_id(self, chunk_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_chunk_status(
        self,
        chunk_id: str,
        status: str,
        quarantine_reason: str | None = None,
    ) -> None:
        now = _now()
        if quarantine_reason:
            self.conn.execute(
                "UPDATE chunks SET status = ?, quarantine_reason = ?, updated_at = ? WHERE id = ?",
                (status, quarantine_reason, now, chunk_id),
            )
        else:
            self.conn.execute(
                "UPDATE chunks SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, chunk_id),
            )
        self.conn.commit()

    def update_chunk_quality(
        self,
        chunk_id: str,
        quality_score: float,
        quality_detail: str,
    ) -> None:
        self.conn.execute(
            "UPDATE chunks SET quality_score = ?, quality_detail = ?, updated_at = ? WHERE id = ?",
            (quality_score, quality_detail, _now(), chunk_id),
        )
        self.conn.commit()

    def mark_chunk_embedded(self, chunk_id: str) -> None:
        now = _now()
        self.conn.execute(
            "UPDATE chunks SET is_embedded = 1, embedded_at = ?, updated_at = ? WHERE id = ?",
            (now, now, chunk_id),
        )
        self.conn.commit()

    def insert_chunks_batch(self, chunks: list[dict[str, Any]]) -> int:
        """Insert multiple chunks in a single transaction. Returns count inserted."""
        if not chunks:
            return 0
        now = _now()
        for c in chunks:
            c.setdefault("created_at", now)
            c.setdefault("updated_at", now)
            c.setdefault("status", "pending")
            c.setdefault("is_embedded", 0)

        columns = list(chunks[0].keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)

        with self.transaction() as cur:
            cur.executemany(
                f"INSERT OR REPLACE INTO chunks ({col_names}) VALUES ({placeholders})",
                [list(c.values()) for c in chunks],
            )
        return len(chunks)

    def iter_pending_embedding_chunks(self, window_size: int = 5000) -> Generator[list[dict[str, Any]], None, None]:
        """Yield pending embedding chunks in windows to avoid loading all into RAM.

        Uses OFFSET 0 every iteration because processed chunks are marked
        is_embedded=1 and drop out of the WHERE clause automatically.
        """
        while True:
            rows = self.conn.execute(
                "SELECT id, text FROM chunks "
                "WHERE status = 'accepted' AND is_embedded = 0 "
                "ORDER BY id LIMIT ?",
                (window_size,),
            ).fetchall()
            if not rows:
                break
            yield [dict(r) for r in rows]

    def mark_chunks_embedded_batch(self, chunk_ids: list[str]) -> None:
        """Mark multiple chunks as embedded in a single transaction."""
        if not chunk_ids:
            return
        now = _now()
        with self.transaction() as cur:
            cur.executemany(
                "UPDATE chunks SET is_embedded = 1, embedded_at = ?, updated_at = ? WHERE id = ?",
                [(now, now, cid) for cid in chunk_ids],
            )

    def get_pending_embedding_chunks(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get accepted chunks that haven't been embedded yet."""
        rows = self.conn.execute(
            "SELECT * FROM chunks WHERE status = 'accepted' AND is_embedded = 0 LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_quarantined_chunks(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM chunks WHERE status = 'quarantined' ORDER BY quality_score ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_chunks_by_file(self, file_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM chunks WHERE file_id = ? ORDER BY id", (file_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def count_chunks(
        self,
        status: str | None = None,
        tool_family: str | None = None,
    ) -> int:
        query = "SELECT COUNT(*) FROM chunks"
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if tool_family:
            conditions.append("tool_family = ?")
            params.append(tool_family)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        row = self.conn.execute(query, params).fetchone()
        return row[0]

    def delete_chunks_by_file(self, file_id: int) -> int:
        """Delete all chunks for a file. Returns deleted count."""
        with self.transaction() as cur:
            cur.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
            return cur.rowcount

    # ── Checkpoint operations ──

    def create_checkpoint(
        self,
        job_id: str,
        job_type: str,
        total_chunks: int,
    ) -> int:
        now = _now()
        with self.transaction() as cur:
            cur.execute(
                """INSERT INTO checkpoints
                   (job_id, job_type, total_chunks, status, started_at, updated_at)
                   VALUES (?, ?, ?, 'running', ?, ?)""",
                (job_id, job_type, total_chunks, now, now),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def update_checkpoint(
        self,
        checkpoint_id: int,
        completed_chunks: int | None = None,
        last_batch_index: int | None = None,
        status: str | None = None,
        error_message: str | None = None,
    ) -> None:
        fields = ["updated_at = ?"]
        values: list[Any] = [_now()]

        if completed_chunks is not None:
            fields.append("completed_chunks = ?")
            values.append(completed_chunks)
        if last_batch_index is not None:
            fields.append("last_batch_index = ?")
            values.append(last_batch_index)
        if status is not None:
            fields.append("status = ?")
            values.append(status)
            if status in ("completed", "failed"):
                fields.append("completed_at = ?")
                values.append(_now())
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)

        values.append(checkpoint_id)
        with self.transaction() as cur:
            cur.execute(
                f"UPDATE checkpoints SET {', '.join(fields)} WHERE id = ?",
                values,
            )

    def get_latest_checkpoint(self, job_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM checkpoints WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None

    # ── Build report operations ──

    def insert_build_report(self, report_data: dict[str, Any]) -> int:
        report_data.setdefault("created_at", _now())
        columns = list(report_data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)

        with self.transaction() as cur:
            cur.execute(
                f"INSERT INTO build_reports ({col_names}) VALUES ({placeholders})",
                list(report_data.values()),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_build_stats(self) -> dict[str, Any]:
        """Get aggregate stats across all chunks."""
        row = self.conn.execute(
            """SELECT
                COUNT(*) as total_chunks,
                SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END) as accepted,
                SUM(CASE WHEN status = 'quarantined' THEN 1 ELSE 0 END) as quarantined,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                AVG(quality_score) as avg_quality,
                SUM(CASE WHEN is_embedded = 1 THEN 1 ELSE 0 END) as embedded
            FROM chunks"""
        ).fetchone()
        return dict(row) if row else {}
