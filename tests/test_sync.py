"""Tests for Phase 3 sync — queue, client, export/import."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.sync.queue import SyncQueue
from backend.sync.client import SyncClient
from backend.sync.export import export_knowledge, import_knowledge


@pytest.fixture
def sync_queue():
    conn = sqlite3.connect(":memory:")
    return SyncQueue(conn)


class TestSyncQueue:
    def test_push_and_get_pending(self, sync_queue):
        sync_queue.push_event("case_closed", "case_records", "C-001", {"title": "test"})
        sync_queue.push_event("case_closed", "case_records", "C-002", {"title": "test2"})
        pending = sync_queue.get_pending()
        assert len(pending) == 2
        assert pending[0]["entity_id"] == "C-001"
        assert pending[1]["entity_id"] == "C-002"

    def test_mark_synced(self, sync_queue):
        eid = sync_queue.push_event("case_closed", "case_records", "C-001", {"title": "t"})
        assert sync_queue.pending_count() == 1
        sync_queue.mark_synced([eid], "http://server:9000")
        assert sync_queue.pending_count() == 0

    def test_pending_count(self, sync_queue):
        assert sync_queue.pending_count() == 0
        sync_queue.push_event("x", "y", "z", {})
        assert sync_queue.pending_count() == 1

    def test_get_pending_limit(self, sync_queue):
        for i in range(10):
            sync_queue.push_event("x", "y", f"e-{i}", {})
        assert len(sync_queue.get_pending(limit=3)) == 3
        assert len(sync_queue.get_pending(limit=100)) == 10


class TestSyncClient:
    def test_disabled_when_no_url(self, sync_queue):
        client = SyncClient(None, sync_queue)
        assert not client.enabled
        assert client.get_status()["status"] == "disabled"

    def test_enabled_when_url_set(self, sync_queue):
        client = SyncClient("http://192.168.1.100:9000", sync_queue)
        assert client.enabled

    def test_status_shows_pending(self, sync_queue):
        sync_queue.push_event("x", "y", "z", {})
        client = SyncClient("http://fake:9000", sync_queue)
        status = client.get_status()
        assert status["pending_events"] == 1
        assert status["status"] == "pending"


class TestExportImport:
    def test_export_creates_zip(self, tmp_path):
        data_dir = tmp_path / "data"
        (data_dir / "sqlite").mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(data_dir / "sqlite" / "zemas.db"))
        conn.execute(
            "CREATE TABLE sessions (session_id TEXT, title TEXT, silo_account TEXT,"
            " silo_tool TEXT, silo_component TEXT, status TEXT,"
            " created_at TEXT, updated_at TEXT, message_count INTEGER)"
        )
        conn.execute(
            "CREATE TABLE messages (session_id TEXT, agent TEXT, content TEXT,"
            " contribution_type TEXT, addressed_to TEXT, created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO sessions VALUES ('s1','Test','SEC','PROVE','InCell',"
            "'active','2026-01-01','2026-01-01',1)"
        )
        conn.execute(
            "INSERT INTO messages VALUES ('s1','analyzer','Hello','NEW_EVIDENCE',"
            "'@You','2026-01-01')"
        )
        conn.commit()
        conn.close()

        out = tmp_path / "export.zip"
        stats = export_knowledge(data_dir, out)
        assert stats["sessions"] == 1
        assert stats["messages"] == 1
        assert out.exists()

    def test_import_merges_sessions(self, tmp_path):
        # Create export
        src = tmp_path / "src"
        (src / "sqlite").mkdir(parents=True)
        conn = sqlite3.connect(str(src / "sqlite" / "zemas.db"))
        conn.execute(
            "CREATE TABLE sessions (session_id TEXT, title TEXT, silo_account TEXT,"
            " silo_tool TEXT, silo_component TEXT, status TEXT,"
            " created_at TEXT, updated_at TEXT, message_count INTEGER)"
        )
        conn.execute("CREATE TABLE messages (session_id TEXT, agent TEXT, content TEXT,"
                     " contribution_type TEXT, addressed_to TEXT, created_at TEXT)")
        conn.execute("INSERT INTO sessions VALUES ('s1','Test','','','','active','2026-01-01','2026-01-01',0)")
        conn.commit()
        conn.close()
        export_knowledge(src, tmp_path / "pack.zip")

        # Import into fresh target
        dst = tmp_path / "dst"
        (dst / "sqlite").mkdir(parents=True)
        conn2 = sqlite3.connect(str(dst / "sqlite" / "zemas.db"))
        conn2.execute(
            "CREATE TABLE sessions (session_id TEXT, title TEXT, silo_account TEXT,"
            " silo_tool TEXT, silo_component TEXT, status TEXT,"
            " created_at TEXT, updated_at TEXT, message_count INTEGER)"
        )
        conn2.execute("CREATE TABLE messages (session_id TEXT, agent TEXT, content TEXT,"
                      " contribution_type TEXT, addressed_to TEXT, created_at TEXT)")
        conn2.commit()
        conn2.close()

        stats = import_knowledge(dst, tmp_path / "pack.zip")
        assert stats["sessions_added"] == 1

        # Import again — should skip duplicate
        stats2 = import_knowledge(dst, tmp_path / "pack.zip")
        assert stats2["sessions_added"] == 0
