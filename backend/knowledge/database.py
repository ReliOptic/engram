"""SQLite structured database for Engram.

Complements ChromaDB with structured queries:
- Case metadata: status, timestamps, account/tool/component filtering
- Cost tracking: per-call token usage and USD cost
- Session/message persistence for chat history
- Structured queries: "all open ClientA cases", "total cost this week"

ChromaDB = similarity search. SQLite = structured queries.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path


class _LockedConnection:
    """Small sqlite3.Connection proxy that serializes shared-connection calls."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def execute(self, *args, **kwargs):
        with self._lock:
            return self._conn.execute(*args, **kwargs)

    def executescript(self, *args, **kwargs):
        with self._lock:
            return self._conn.executescript(*args, **kwargs)

    def commit(self):
        with self._lock:
            return self._conn.commit()

    def close(self):
        with self._lock:
            return self._conn.close()

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._conn.row_factory = value


class EngramDB:
    """SQLite database for structured case and cost data (EngramDB)."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.RLock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        raw_conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn = _LockedConnection(raw_conn, self._lock)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    account TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    component TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    resolution TEXT DEFAULT '',
                    silo_key TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    closed_at TEXT DEFAULT NULL
                );

                CREATE TABLE IF NOT EXISTS cost_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_usd REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cases_account ON cases(account);
                CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
                CREATE INDEX IF NOT EXISTS idx_cases_silo ON cases(silo_key);
                CREATE INDEX IF NOT EXISTS idx_cost_case ON cost_log(case_id);
                CREATE INDEX IF NOT EXISTS idx_cost_model ON cost_log(model);

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    silo_account TEXT NOT NULL DEFAULT '',
                    silo_tool TEXT NOT NULL DEFAULT '',
                    silo_component TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    contribution_type TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    addressed_to TEXT DEFAULT '',
                    timestamp TEXT NOT NULL,
                    silo_account TEXT NOT NULL DEFAULT '',
                    silo_tool TEXT NOT NULL DEFAULT '',
                    silo_component TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
                CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            """)

    # --- Cases ---

    def create_case(
        self,
        case_id: str,
        account: str,
        tool: str,
        component: str,
        title: str,
    ) -> str:
        silo_key = f"{account}_{tool}_{component}"
        now = datetime.now(tz=UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO cases (case_id, account, tool, component, title, silo_key, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (case_id, account, tool, component, title, silo_key, now),
            )
            self._conn.commit()
        return case_id

    def close_case(self, case_id: str, resolution: str) -> None:
        now = datetime.now(tz=UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE cases SET status='closed', resolution=?, closed_at=? WHERE case_id=?",
                (resolution, now, case_id),
            )
            self._conn.commit()

    def get_case(self, case_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM cases WHERE case_id=?", (case_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_cases(
        self,
        account: str | None = None,
        tool: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        query = "SELECT * FROM cases WHERE 1=1"
        params: list = []

        if account:
            query += " AND account=?"
            params.append(account)
        if tool:
            query += " AND tool=?"
            params.append(tool)
        if status:
            query += " AND status=?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # --- Cost Tracking ---

    def log_cost(
        self,
        case_id: str,
        role: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
    ) -> None:
        now = datetime.now(tz=UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO cost_log (case_id, role, model, prompt_tokens, completion_tokens, cost_usd, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (case_id, role, model, prompt_tokens, completion_tokens, cost_usd, now),
            )
            self._conn.commit()

    def get_case_cost(self, case_id: str) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT "
                "  COUNT(*) as call_count, "
                "  COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens, "
                "  COALESCE(SUM(completion_tokens), 0) as total_completion_tokens, "
                "  COALESCE(SUM(cost_usd), 0.0) as total_cost_usd "
                "FROM cost_log WHERE case_id=?",
                (case_id,),
            ).fetchone()
        return dict(row)

    def get_cost_summary_by_model(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT "
                "  model, "
                "  COUNT(*) as call_count, "
                "  SUM(prompt_tokens) as total_prompt_tokens, "
                "  SUM(completion_tokens) as total_completion_tokens, "
                "  SUM(cost_usd) as total_cost_usd "
                "FROM cost_log GROUP BY model ORDER BY total_cost_usd DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Sessions ---

    def create_session(
        self,
        title: str = "",
        silo_account: str = "",
        silo_tool: str = "",
        silo_component: str = "",
    ) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (session_id, title, silo_account, silo_tool, silo_component, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
                (session_id, title, silo_account, silo_tool, silo_component, now, now),
            )
            self._conn.commit()
        return session_id

    def list_sessions(self, status: str | None = None, limit: int = 50) -> list[dict]:
        query = "SELECT * FROM sessions WHERE 1=1"
        params: list = []
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_session_title(self, session_id: str, title: str) -> None:
        now = datetime.now(tz=UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET title=?, updated_at=? WHERE session_id=?",
                (title, now, session_id),
            )
            self._conn.commit()

    def archive_session(self, session_id: str) -> None:
        now = datetime.now(tz=UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET status='archived', updated_at=? WHERE session_id=?",
                (now, session_id),
            )
            self._conn.commit()

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
            self._conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
            self._conn.commit()

    # --- Messages ---

    def add_message(
        self,
        session_id: str,
        agent: str,
        content: str,
        contribution_type: str = "",
        addressed_to: str = "",
        silo_account: str = "",
        silo_tool: str = "",
        silo_component: str = "",
    ) -> int:
        now = datetime.now(tz=UTC).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO messages (session_id, agent, contribution_type, content, addressed_to, timestamp, silo_account, silo_tool, silo_component) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, agent, contribution_type, content, addressed_to, now, silo_account, silo_tool, silo_component),
            )
            # Update session's message_count and updated_at
            self._conn.execute(
                "UPDATE sessions SET message_count = message_count + 1, updated_at=? WHERE session_id=?",
                (now, session_id),
            )
            self._conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    def get_messages(self, session_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        with self._lock:
            self._conn.close()
