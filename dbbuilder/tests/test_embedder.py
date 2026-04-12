"""Tests for batch embedder."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from db_builder.database import DatabaseManager
from db_builder.embedding.client import EmbeddingClient, EmbeddingError, EmbeddingResult
from db_builder.embedding.embedder import BatchEmbedder, BatchProgress


@pytest.fixture
def db(sample_db_path: Path) -> DatabaseManager:
    manager = DatabaseManager(sample_db_path)
    manager.init_schema()
    yield manager
    manager.close()


@pytest.fixture
def mock_client() -> EmbeddingClient:
    client = MagicMock(spec=EmbeddingClient)
    return client


def _insert_accepted_chunks(db: DatabaseManager, count: int) -> list[str]:
    """Insert N accepted, non-embedded chunks. Returns chunk IDs."""
    fid = db.insert_file("test.pdf", "hash", 100, "manual")
    ids = []
    for i in range(count):
        cid = f"chunk-{i:03d}"
        db.insert_chunk({
            "id": cid, "file_id": fid,
            "text": f"Chunk text number {i} about PROVE system.",
            "token_count": 10, "chunk_type": "manual",
            "source_file": "test.pdf", "source_type": "manual",
            "status": "accepted", "silo_key": "", "language": "en",
        })
        ids.append(cid)
    return ids


def _make_embed_response(count: int, tokens_per_chunk: int = 10) -> EmbeddingResult:
    return EmbeddingResult(
        embeddings=[[0.1, 0.2, 0.3] for _ in range(count)],
        model="openai/text-embedding-3-small",
        prompt_tokens=count * tokens_per_chunk,
        total_tokens=count * tokens_per_chunk,
    )


class TestBatchEmbedder:
    def test_embeds_all_chunks(self, db: DatabaseManager, mock_client):
        ids = _insert_accepted_chunks(db, 5)
        mock_client.embed.return_value = _make_embed_response(5)

        embedder = BatchEmbedder(db, mock_client, batch_size=10)
        progress = embedder.run()

        assert progress.total_chunks == 5
        assert progress.completed_chunks == 5
        assert progress.failed_chunks == 0

        # All chunks should be marked as embedded
        for cid in ids:
            c = db.get_chunk_by_id(cid)
            assert c["is_embedded"] == 1
            assert c["embedded_at"] is not None

    def test_batch_splitting(self, db: DatabaseManager, mock_client):
        _insert_accepted_chunks(db, 10)
        mock_client.embed.side_effect = [
            _make_embed_response(3),
            _make_embed_response(3),
            _make_embed_response(3),
            _make_embed_response(1),
        ]

        embedder = BatchEmbedder(db, mock_client, batch_size=3)
        progress = embedder.run()

        assert progress.total_chunks == 10
        assert progress.completed_chunks == 10
        assert progress.total_batches == 4
        assert mock_client.embed.call_count == 4

    def test_no_chunks_to_embed(self, db: DatabaseManager, mock_client):
        # No chunks inserted
        embedder = BatchEmbedder(db, mock_client, batch_size=10)
        progress = embedder.run()

        assert progress.total_chunks == 0
        assert progress.completed_chunks == 0
        mock_client.embed.assert_not_called()

    def test_skips_already_embedded(self, db: DatabaseManager, mock_client):
        fid = db.insert_file("test.pdf", "hash", 100, "manual")
        # One embedded, one not
        db.insert_chunk({
            "id": "already", "file_id": fid, "text": "old",
            "token_count": 5, "chunk_type": "manual",
            "source_file": "test.pdf", "source_type": "manual",
            "status": "accepted", "is_embedded": 1,
            "silo_key": "", "language": "en",
        })
        db.insert_chunk({
            "id": "new", "file_id": fid, "text": "new chunk",
            "token_count": 5, "chunk_type": "manual",
            "source_file": "test.pdf", "source_type": "manual",
            "status": "accepted", "is_embedded": 0,
            "silo_key": "", "language": "en",
        })
        mock_client.embed.return_value = _make_embed_response(1)

        embedder = BatchEmbedder(db, mock_client, batch_size=10)
        progress = embedder.run()

        assert progress.total_chunks == 1  # only the new one
        assert progress.completed_chunks == 1

    def test_skips_quarantined(self, db: DatabaseManager, mock_client):
        fid = db.insert_file("test.pdf", "hash", 100, "manual")
        db.insert_chunk({
            "id": "quarantined", "file_id": fid, "text": "bad",
            "token_count": 5, "chunk_type": "manual",
            "source_file": "test.pdf", "source_type": "manual",
            "status": "quarantined", "silo_key": "", "language": "en",
        })
        db.insert_chunk({
            "id": "good", "file_id": fid, "text": "good chunk",
            "token_count": 5, "chunk_type": "manual",
            "source_file": "test.pdf", "source_type": "manual",
            "status": "accepted", "silo_key": "", "language": "en",
        })
        mock_client.embed.return_value = _make_embed_response(1)

        embedder = BatchEmbedder(db, mock_client, batch_size=10)
        progress = embedder.run()

        assert progress.total_chunks == 1

    def test_checkpoint_created(self, db: DatabaseManager, mock_client):
        _insert_accepted_chunks(db, 5)
        mock_client.embed.return_value = _make_embed_response(5)

        embedder = BatchEmbedder(db, mock_client, batch_size=10)
        progress = embedder.run()

        # Should have a completed checkpoint
        rows = db.conn.execute(
            "SELECT * FROM checkpoints ORDER BY id DESC LIMIT 1"
        ).fetchall()
        assert len(rows) == 1
        cp = dict(rows[0])
        assert cp["status"] == "completed"
        assert cp["completed_chunks"] == 5
        assert cp["total_chunks"] == 5

    def test_handles_batch_failure(self, db: DatabaseManager, mock_client):
        _insert_accepted_chunks(db, 6)
        mock_client.embed.side_effect = [
            _make_embed_response(3),  # batch 0 succeeds
            EmbeddingError("API down"),  # batch 1 fails
        ]

        embedder = BatchEmbedder(db, mock_client, batch_size=3)
        progress = embedder.run()

        assert progress.completed_chunks == 3
        assert progress.failed_chunks == 3

        # Check checkpoint failures recorded
        failures = db.conn.execute(
            "SELECT * FROM checkpoint_failures"
        ).fetchall()
        assert len(failures) == 3

    def test_cancel_stops_gracefully(self, db: DatabaseManager, mock_client):
        _insert_accepted_chunks(db, 10)

        def embed_and_cancel(texts):
            embedder.cancel()  # cancel after first batch
            return _make_embed_response(len(texts))

        mock_client.embed.side_effect = embed_and_cancel

        embedder = BatchEmbedder(db, mock_client, batch_size=3)
        progress = embedder.run()

        # Should have processed only the first batch
        assert progress.completed_chunks == 3
        assert progress.total_chunks == 10

        # Checkpoint should be paused
        cp = db.conn.execute(
            "SELECT status FROM checkpoints ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert cp["status"] == "paused"

    def test_progress_callback(self, db: DatabaseManager, mock_client):
        _insert_accepted_chunks(db, 5)
        mock_client.embed.return_value = _make_embed_response(5)

        progress_updates = []
        embedder = BatchEmbedder(
            db, mock_client, batch_size=5,
            on_progress=lambda p: progress_updates.append(p.percent),
        )
        embedder.run()

        assert len(progress_updates) == 1
        assert progress_updates[0] == 100.0

    def test_cost_estimation(self, db: DatabaseManager, mock_client):
        _insert_accepted_chunks(db, 5)
        mock_client.embed.return_value = EmbeddingResult(
            embeddings=[[0.1]] * 5,
            model="test",
            prompt_tokens=1000,
            total_tokens=1000,
        )

        embedder = BatchEmbedder(
            db, mock_client, batch_size=10,
            cost_per_million_input=0.02,
        )
        progress = embedder.run()

        # 1000 tokens * $0.02/1M = $0.00002
        assert abs(progress.estimated_cost_usd - 0.00002) < 0.000001

    def test_checkpoint_interval(self, db: DatabaseManager, mock_client):
        _insert_accepted_chunks(db, 10)
        mock_client.embed.return_value = _make_embed_response(2)

        # checkpoint_interval=2 means save every 2 batches
        embedder = BatchEmbedder(
            db, mock_client, batch_size=2, checkpoint_interval=2,
        )
        embedder.run()

        cp = db.conn.execute(
            "SELECT * FROM checkpoints ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert dict(cp)["status"] == "completed"


class TestBatchProgress:
    def test_percent_calculation(self):
        p = BatchProgress(total_chunks=100, completed_chunks=50,
                          current_batch=5, total_batches=10)
        assert p.percent == 50.0

    def test_percent_zero_total(self):
        p = BatchProgress(total_chunks=0, completed_chunks=0,
                          current_batch=0, total_batches=0)
        assert p.percent == 100.0
