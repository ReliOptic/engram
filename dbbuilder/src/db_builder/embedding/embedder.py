"""Batch embedding engine with checkpoint/resume support.

Processes accepted chunks from SQLite in batches,
embeds via OpenRouter, and updates chunk status.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Callable

from db_builder.database import DatabaseManager
from db_builder.embedding.client import EmbeddingClient, EmbeddingError

logger = logging.getLogger(__name__)


@dataclass
class BatchProgress:
    """Progress snapshot for UI callbacks."""

    total_chunks: int
    completed_chunks: int
    current_batch: int
    total_batches: int
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    failed_chunks: int = 0

    @property
    def percent(self) -> float:
        if self.total_chunks == 0:
            return 100.0
        return (self.completed_chunks / self.total_chunks) * 100


class BatchEmbedder:
    """Embeds chunks in batches with checkpoint/resume.

    Flow:
        1. Query accepted, non-embedded chunks from SQLite
        2. Split into batches of `batch_size`
        3. Call EmbeddingClient.embed() per batch
        4. Update SQLite: mark chunks as embedded
        5. Save checkpoint every `checkpoint_interval` batches
        6. On failure: save progress, can resume later
    """

    def __init__(
        self,
        db: DatabaseManager,
        client: EmbeddingClient,
        batch_size: int = 100,
        checkpoint_interval: int = 100,
        cost_per_million_input: float = 0.02,
        on_progress: Callable[[BatchProgress], None] | None = None,
    ):
        self.db = db
        self.client = client
        self.batch_size = batch_size
        self.checkpoint_interval = checkpoint_interval
        self.cost_per_million = cost_per_million_input
        self.on_progress = on_progress
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation. Completes current batch then stops."""
        self._cancelled = True

    def run(self, job_type: str = "full_build") -> BatchProgress:
        """Run embedding for all pending chunks. Streams from DB to avoid OOM."""
        self._cancelled = False

        # Count total without loading into RAM
        row = self.db.conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE status = 'accepted' AND is_embedded = 0"
        ).fetchone()
        total = row[0]

        if total == 0:
            logger.info("No chunks to embed.")
            return BatchProgress(
                total_chunks=0, completed_chunks=0,
                current_batch=0, total_batches=0,
            )

        # Create checkpoint
        job_id = str(uuid.uuid4())
        cp_id = self.db.create_checkpoint(job_id, job_type, total)

        total_batches = (total + self.batch_size - 1) // self.batch_size
        progress = BatchProgress(
            total_chunks=total,
            completed_chunks=0,
            current_batch=0,
            total_batches=total_batches,
        )

        logger.info(
            "Starting embedding: %d chunks in ~%d batches (batch_size=%d)",
            total, total_batches, self.batch_size,
        )

        batch_idx = 0
        for window in self._iter_pending_windows(window_size=5000):
            # Split window into batches
            for i in range(0, len(window), self.batch_size):
                if self._cancelled:
                    logger.info("Embedding cancelled at batch %d", batch_idx)
                    self.db.update_checkpoint(
                        cp_id, status="paused",
                        completed_chunks=progress.completed_chunks,
                        last_batch_index=batch_idx,
                    )
                    return progress

                batch = window[i:i + self.batch_size]
                try:
                    embedded_count, tokens = self._process_batch(batch)
                    progress.completed_chunks += embedded_count
                    progress.total_tokens += tokens
                    progress.current_batch = batch_idx + 1
                    progress.estimated_cost_usd = (
                        progress.total_tokens / 1_000_000 * self.cost_per_million
                    )
                except EmbeddingError as e:
                    logger.error("Batch %d failed: %s", batch_idx, e)
                    progress.failed_chunks += len(batch)
                    for chunk in batch:
                        self.db.conn.execute(
                            """INSERT INTO checkpoint_failures
                               (checkpoint_id, chunk_id, error_message, created_at)
                               VALUES (?, ?, ?, datetime('now'))""",
                            (cp_id, chunk["id"], str(e)),
                        )
                    self.db.conn.commit()

                # Checkpoint save
                if (batch_idx + 1) % self.checkpoint_interval == 0:
                    self.db.update_checkpoint(
                        cp_id,
                        completed_chunks=progress.completed_chunks,
                        last_batch_index=batch_idx + 1,
                    )
                    logger.info(
                        "Checkpoint saved: %d/%d chunks (batch %d)",
                        progress.completed_chunks, total, batch_idx + 1,
                    )

                if self.on_progress:
                    self.on_progress(progress)

                batch_idx += 1

        # Final checkpoint
        final_status = "paused" if self._cancelled else "completed"
        self.db.update_checkpoint(
            cp_id,
            status=final_status,
            completed_chunks=progress.completed_chunks,
            last_batch_index=progress.current_batch,
            error_message=(
                f"{progress.failed_chunks} chunks failed"
                if progress.failed_chunks > 0 else None
            ),
        )

        logger.info(
            "Embedding %s: %d/%d chunks, %d tokens, $%.4f, %d failed",
            final_status, progress.completed_chunks, total,
            progress.total_tokens, progress.estimated_cost_usd,
            progress.failed_chunks,
        )

        return progress

    def _iter_pending_windows(self, window_size: int = 5000):
        """Yield windows of pending chunks from DB without loading all into RAM.

        Uses OFFSET 0 every iteration because processed chunks are marked
        is_embedded=1 and drop out of the WHERE clause automatically.
        """
        while True:
            rows = self.db.conn.execute(
                "SELECT id, text FROM chunks "
                "WHERE status = 'accepted' AND is_embedded = 0 "
                "ORDER BY id LIMIT ?",
                (window_size,),
            ).fetchall()
            if not rows:
                break
            yield [dict(r) for r in rows]

    def _process_batch(self, batch: list[dict]) -> tuple[int, int]:
        """Embed one batch. Returns (embedded_count, total_tokens)."""
        texts = [chunk["text"] for chunk in batch]
        result = self.client.embed(texts)

        # Update each chunk in SQLite
        for chunk, embedding in zip(batch, result.embeddings):
            self.db.mark_chunk_embedded(chunk["id"])

        return len(batch), result.total_tokens
