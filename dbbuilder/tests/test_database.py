"""Tests for SQLite database manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from db_builder.database import DatabaseManager, SCHEMA_VERSION


@pytest.fixture
def db(sample_db_path: Path) -> DatabaseManager:
    """Initialized database for testing."""
    manager = DatabaseManager(sample_db_path)
    manager.init_schema()
    yield manager
    manager.close()


class TestSchemaInit:
    def test_creates_all_tables(self, db: DatabaseManager):
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        assert "files" in table_names
        assert "chunks" in table_names
        assert "checkpoints" in table_names
        assert "checkpoint_failures" in table_names
        assert "build_reports" in table_names
        assert "_schema_version" in table_names

    def test_schema_version_set(self, db: DatabaseManager):
        assert db.get_schema_version() == SCHEMA_VERSION

    def test_init_idempotent(self, db: DatabaseManager):
        db.init_schema()  # second call
        assert db.get_schema_version() == SCHEMA_VERSION

    def test_foreign_keys_enabled(self, db: DatabaseManager):
        row = db.conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1


class TestFileOperations:
    def test_insert_and_get(self, db: DatabaseManager):
        file_id = db.insert_file(
            file_path="manuals/PROVE_v3.pdf",
            file_hash="abc123",
            file_size=1024,
            source_type="manual",
        )
        assert file_id > 0

        f = db.get_file_by_id(file_id)
        assert f is not None
        assert f["file_path"] == "manuals/PROVE_v3.pdf"
        assert f["file_hash"] == "abc123"
        assert f["file_size"] == 1024
        assert f["source_type"] == "manual"
        assert f["status"] == "pending"

    def test_get_by_path(self, db: DatabaseManager):
        db.insert_file("weekly/CW15.xlsx", "def456", 2048, "weekly")
        f = db.get_file_by_path("weekly/CW15.xlsx")
        assert f is not None
        assert f["source_type"] == "weekly"

    def test_get_nonexistent_returns_none(self, db: DatabaseManager):
        assert db.get_file_by_path("nope.txt") is None
        assert db.get_file_by_id(9999) is None

    def test_unique_path_constraint(self, db: DatabaseManager):
        db.insert_file("a.pdf", "h1", 100, "manual")
        with pytest.raises(Exception):
            db.insert_file("a.pdf", "h2", 200, "manual")

    def test_update_status(self, db: DatabaseManager):
        fid = db.insert_file("x.pdf", "h", 100, "manual")
        db.update_file_status(fid, "parsed", chunk_count=42, avg_quality=0.85)

        f = db.get_file_by_id(fid)
        assert f["status"] == "parsed"
        assert f["chunk_count"] == 42
        assert f["avg_quality"] == 0.85

    def test_completed_sets_last_built(self, db: DatabaseManager):
        fid = db.insert_file("x.pdf", "h", 100, "manual")
        db.update_file_status(fid, "completed")
        f = db.get_file_by_id(fid)
        assert f["last_built_at"] is not None

    def test_update_hash(self, db: DatabaseManager):
        fid = db.insert_file("x.pdf", "old_hash", 100, "manual")
        db.update_file_hash(fid, "new_hash", 200)
        f = db.get_file_by_id(fid)
        assert f["file_hash"] == "new_hash"
        assert f["file_size"] == 200

    def test_list_files(self, db: DatabaseManager):
        db.insert_file("a.pdf", "h1", 100, "manual")
        db.insert_file("b.xlsx", "h2", 200, "weekly")
        assert len(db.list_files()) == 2

    def test_list_files_by_status(self, db: DatabaseManager):
        fid = db.insert_file("a.pdf", "h1", 100, "manual")
        db.insert_file("b.xlsx", "h2", 200, "weekly")
        db.update_file_status(fid, "completed")
        assert len(db.list_files(status="completed")) == 1
        assert len(db.list_files(status="pending")) == 1

    def test_detected_mode(self, db: DatabaseManager):
        fid = db.insert_file("w.xlsx", "h", 100, "weekly", detected_mode="weekly_new")
        f = db.get_file_by_id(fid)
        assert f["detected_mode"] == "weekly_new"


class TestChunkOperations:
    def _make_chunk(self, db: DatabaseManager, chunk_id: str = "m-abc123_p01_001") -> tuple[int, str]:
        fid = db.insert_file("test.pdf", "hash", 100, "manual")
        cid = db.insert_chunk({
            "id": chunk_id,
            "file_id": fid,
            "text": "Sample chunk text about TIS recalibration.",
            "token_count": 42,
            "chunk_type": "manual",
            "source_file": "test.pdf",
            "source_type": "manual",
            "tool_family": "PROVE",
            "silo_key": "",
            "language": "en",
        })
        return fid, cid

    def test_insert_and_get(self, db: DatabaseManager):
        _, cid = self._make_chunk(db)
        c = db.get_chunk_by_id(cid)
        assert c is not None
        assert c["text"] == "Sample chunk text about TIS recalibration."
        assert c["tool_family"] == "PROVE"
        assert c["chunk_type"] == "manual"
        assert c["status"] == "pending"
        assert c["is_embedded"] == 0

    def test_update_status(self, db: DatabaseManager):
        _, cid = self._make_chunk(db)
        db.update_chunk_status(cid, "accepted")
        c = db.get_chunk_by_id(cid)
        assert c["status"] == "accepted"

    def test_quarantine(self, db: DatabaseManager):
        _, cid = self._make_chunk(db)
        db.update_chunk_status(cid, "quarantined", quarantine_reason="low quality: 0.3")
        c = db.get_chunk_by_id(cid)
        assert c["status"] == "quarantined"
        assert c["quarantine_reason"] == "low quality: 0.3"

    def test_update_quality(self, db: DatabaseManager):
        _, cid = self._make_chunk(db)
        db.update_chunk_quality(cid, 0.87, '{"length":0.9,"coherence":0.8}')
        c = db.get_chunk_by_id(cid)
        assert c["quality_score"] == 0.87
        assert '"length"' in c["quality_detail"]

    def test_mark_embedded(self, db: DatabaseManager):
        _, cid = self._make_chunk(db)
        db.update_chunk_status(cid, "accepted")
        db.mark_chunk_embedded(cid)
        c = db.get_chunk_by_id(cid)
        assert c["is_embedded"] == 1
        assert c["embedded_at"] is not None

    def test_get_pending_embedding(self, db: DatabaseManager):
        fid, _ = self._make_chunk(db, "chunk1")
        db.update_chunk_status("chunk1", "accepted")
        # Insert a second chunk that's already embedded
        db.insert_chunk({
            "id": "chunk2", "file_id": fid, "text": "embedded",
            "token_count": 10, "chunk_type": "manual", "source_file": "test.pdf",
            "source_type": "manual", "status": "accepted",
            "is_embedded": 1, "silo_key": "", "language": "en",
        })
        pending = db.get_pending_embedding_chunks()
        assert len(pending) == 1
        assert pending[0]["id"] == "chunk1"

    def test_get_quarantined(self, db: DatabaseManager):
        _, cid = self._make_chunk(db)
        db.update_chunk_status(cid, "quarantined", "bad")
        q = db.get_quarantined_chunks()
        assert len(q) == 1

    def test_get_by_file(self, db: DatabaseManager):
        fid, _ = self._make_chunk(db)
        chunks = db.get_chunks_by_file(fid)
        assert len(chunks) == 1

    def test_count_chunks(self, db: DatabaseManager):
        fid = db.insert_file("count_test.pdf", "h", 100, "manual")
        db.insert_chunk({
            "id": "c1", "file_id": fid, "text": "x", "token_count": 10,
            "chunk_type": "manual", "source_file": "count_test.pdf",
            "source_type": "manual", "silo_key": "", "language": "en",
        })
        db.insert_chunk({
            "id": "c2", "file_id": fid, "text": "y", "token_count": 10,
            "chunk_type": "manual", "source_file": "count_test.pdf",
            "source_type": "manual", "silo_key": "", "language": "en",
        })
        assert db.count_chunks() == 2

    def test_count_by_tool_family(self, db: DatabaseManager):
        fid = db.insert_file("t.pdf", "h", 100, "manual")
        db.insert_chunk({
            "id": "c1", "file_id": fid, "text": "x", "token_count": 10,
            "chunk_type": "manual", "source_file": "t.pdf", "source_type": "manual",
            "tool_family": "PROVE", "silo_key": "", "language": "en",
        })
        db.insert_chunk({
            "id": "c2", "file_id": fid, "text": "y", "token_count": 10,
            "chunk_type": "manual", "source_file": "t.pdf", "source_type": "manual",
            "tool_family": "AIMS", "silo_key": "", "language": "en",
        })
        assert db.count_chunks(tool_family="PROVE") == 1
        assert db.count_chunks(tool_family="AIMS") == 1

    def test_delete_by_file(self, db: DatabaseManager):
        fid, _ = self._make_chunk(db)
        deleted = db.delete_chunks_by_file(fid)
        assert deleted == 1
        assert db.get_chunks_by_file(fid) == []

    def test_upsert_replaces(self, db: DatabaseManager):
        """INSERT OR REPLACE ensures rebuild safety."""
        fid, cid = self._make_chunk(db)
        db.insert_chunk({
            "id": cid, "file_id": fid, "text": "Updated text",
            "token_count": 5, "chunk_type": "manual", "source_file": "test.pdf",
            "source_type": "manual", "silo_key": "", "language": "en",
        })
        c = db.get_chunk_by_id(cid)
        assert c["text"] == "Updated text"

    def test_insert_chunks_batch(self, db: DatabaseManager):
        fid = db.insert_file("batch.pdf", "h", 100, "manual")
        chunks = [
            {
                "id": f"batch-{i:04d}",
                "file_id": fid,
                "text": f"Batch chunk {i}",
                "token_count": 10,
                "chunk_type": "manual",
                "source_file": "batch.pdf",
                "source_type": "manual",
                "silo_key": "",
                "language": "en",
            }
            for i in range(50)
        ]
        inserted = db.insert_chunks_batch(chunks)
        assert inserted == 50
        assert db.count_chunks() == 50
        c = db.get_chunk_by_id("batch-0000")
        assert c is not None
        assert c["text"] == "Batch chunk 0"
        assert c["status"] == "pending"

    def test_iter_pending_embedding_chunks_windowing(self, db: DatabaseManager):
        fid = db.insert_file("window.pdf", "h", 100, "manual")
        chunks = [
            {
                "id": f"win-{i:04d}",
                "file_id": fid,
                "text": f"Window chunk {i}",
                "token_count": 5,
                "chunk_type": "manual",
                "source_file": "window.pdf",
                "source_type": "manual",
                "status": "accepted",
                "silo_key": "",
                "language": "en",
            }
            for i in range(25)
        ]
        db.insert_chunks_batch(chunks)

        windows = list(db.iter_pending_embedding_chunks(window_size=10))
        assert len(windows) == 3
        assert len(windows[0]) == 10
        assert len(windows[1]) == 10
        assert len(windows[2]) == 5
        # All 25 unique ids across windows
        all_ids = [row["id"] for w in windows for row in w]
        assert len(all_ids) == 25
        assert len(set(all_ids)) == 25

    def test_mark_chunks_embedded_batch(self, db: DatabaseManager):
        fid = db.insert_file("embed.pdf", "h", 100, "manual")
        chunks = [
            {
                "id": f"emb-{i:04d}",
                "file_id": fid,
                "text": f"Embed chunk {i}",
                "token_count": 5,
                "chunk_type": "manual",
                "source_file": "embed.pdf",
                "source_type": "manual",
                "status": "accepted",
                "silo_key": "",
                "language": "en",
            }
            for i in range(10)
        ]
        db.insert_chunks_batch(chunks)

        # Mark first 7 as embedded
        ids_to_mark = [f"emb-{i:04d}" for i in range(7)]
        db.mark_chunks_embedded_batch(ids_to_mark)

        # 3 remain unembedded
        pending = db.get_pending_embedding_chunks(limit=100)
        assert len(pending) == 3

        # Verify marked ones have is_embedded=1 and embedded_at set
        c = db.get_chunk_by_id("emb-0000")
        assert c["is_embedded"] == 1
        assert c["embedded_at"] is not None

        # Verify unmarked ones still have is_embedded=0
        c = db.get_chunk_by_id("emb-0007")
        assert c["is_embedded"] == 0
        assert c["embedded_at"] is None


class TestCheckpointOperations:
    def test_create_and_get(self, db: DatabaseManager):
        cp_id = db.create_checkpoint("job-001", "full_build", 1000)
        assert cp_id > 0
        cp = db.get_latest_checkpoint("job-001")
        assert cp is not None
        assert cp["total_chunks"] == 1000
        assert cp["status"] == "running"
        assert cp["completed_chunks"] == 0

    def test_update_progress(self, db: DatabaseManager):
        cp_id = db.create_checkpoint("job-002", "full_build", 500)
        db.update_checkpoint(cp_id, completed_chunks=200, last_batch_index=2)
        cp = db.get_latest_checkpoint("job-002")
        assert cp["completed_chunks"] == 200
        assert cp["last_batch_index"] == 2

    def test_complete(self, db: DatabaseManager):
        cp_id = db.create_checkpoint("job-003", "full_build", 100)
        db.update_checkpoint(cp_id, status="completed", completed_chunks=100)
        cp = db.get_latest_checkpoint("job-003")
        assert cp["status"] == "completed"
        assert cp["completed_at"] is not None

    def test_fail_with_error(self, db: DatabaseManager):
        cp_id = db.create_checkpoint("job-004", "full_build", 100)
        db.update_checkpoint(cp_id, status="failed", error_message="API down")
        cp = db.get_latest_checkpoint("job-004")
        assert cp["status"] == "failed"
        assert cp["error_message"] == "API down"


class TestBuildStats:
    def test_empty_stats(self, db: DatabaseManager):
        stats = db.get_build_stats()
        assert stats["total_chunks"] == 0

    def test_aggregate_stats(self, db: DatabaseManager):
        fid = db.insert_file("t.pdf", "h", 100, "manual")
        for i, (status, quality, embedded) in enumerate([
            ("accepted", 0.9, 1),
            ("accepted", 0.8, 0),
            ("quarantined", 0.3, 0),
        ]):
            db.insert_chunk({
                "id": f"c{i}", "file_id": fid, "text": "x",
                "token_count": 10, "chunk_type": "manual",
                "source_file": "t.pdf", "source_type": "manual",
                "status": status, "quality_score": quality,
                "is_embedded": embedded, "silo_key": "", "language": "en",
            })

        stats = db.get_build_stats()
        assert stats["total_chunks"] == 3
        assert stats["accepted"] == 2
        assert stats["quarantined"] == 1
        assert stats["embedded"] == 1
        assert abs(stats["avg_quality"] - 0.6667) < 0.01
