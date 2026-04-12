"""Sync queue — tracks local changes for push to sync server.

Every case close, session creation, and message save appends an event
to the queue. When the sync server is reachable, pending events are
pushed in order. If the server is offline, events accumulate locally
and are pushed when connectivity returns.

The queue lives in the same SQLite database (engram.db) as sessions
and cases — no extra files to manage.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

SYNC_QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    collection TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    synced_at TEXT,
    sync_server TEXT
);
CREATE INDEX IF NOT EXISTS idx_sync_queue_pending
    ON sync_queue(synced_at) WHERE synced_at IS NULL;
"""


class SyncQueue:
    """Append-only event queue for offline-first sync."""

    def __init__(self, db_conn):
        self.conn = db_conn
        self._ensure_schema()

    def _ensure_schema(self):
        self.conn.executescript(SYNC_QUEUE_SCHEMA)
        self.conn.commit()

    def push_event(
        self,
        event_type: str,
        collection: str,
        entity_id: str,
        payload: dict[str, Any],
    ) -> int:
        """Record a local change for future sync.

        Args:
            event_type: 'case_closed', 'session_created', 'message_added',
                        'chunk_added', 'manual_imported'
            collection: 'case_records', 'traces', 'sessions', 'manuals'
            entity_id: case_id, session_id, or chunk_id
            payload: full data dict to send to server

        Returns:
            Queue entry ID.
        """
        cur = self.conn.execute(
            """INSERT INTO sync_queue
               (event_type, collection, entity_id, payload, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                event_type,
                collection,
                entity_id,
                json.dumps(payload, default=str),
                datetime.now(tz=UTC).isoformat(),
            ),
        )
        self.conn.commit()
        entry_id = cur.lastrowid
        logger.debug(
            "Sync queue: %s %s/%s (id=%d)",
            event_type, collection, entity_id, entry_id,
        )
        return entry_id

    def get_pending(self, limit: int = 100) -> list[dict]:
        """Get unsynced events, oldest first."""
        rows = self.conn.execute(
            """SELECT id, event_type, collection, entity_id, payload, created_at
               FROM sync_queue
               WHERE synced_at IS NULL
               ORDER BY id
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "event_type": r[1],
                "collection": r[2],
                "entity_id": r[3],
                "payload": json.loads(r[4]),
                "created_at": r[5],
            }
            for r in rows
        ]

    def mark_synced(self, entry_ids: list[int], server_url: str) -> None:
        """Mark events as successfully pushed to server."""
        if not entry_ids:
            return
        now = datetime.now(tz=UTC).isoformat()
        placeholders = ",".join("?" * len(entry_ids))
        self.conn.execute(
            f"""UPDATE sync_queue
                SET synced_at = ?, sync_server = ?
                WHERE id IN ({placeholders})""",
            [now, server_url] + entry_ids,
        )
        self.conn.commit()
        logger.info("Marked %d events as synced to %s", len(entry_ids), server_url)

    def pending_count(self) -> int:
        """Number of unsynced events."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM sync_queue WHERE synced_at IS NULL"
        ).fetchone()
        return row[0] if row else 0

    def purge_synced(self, older_than_days: int = 30) -> int:
        """Remove old synced events to keep the DB lean."""
        cur = self.conn.execute(
            """DELETE FROM sync_queue
               WHERE synced_at IS NOT NULL
               AND synced_at < datetime('now', ?)""",
            (f"-{older_than_days} days",),
        )
        self.conn.commit()
        return cur.rowcount
