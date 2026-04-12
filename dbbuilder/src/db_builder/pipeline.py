"""Pipeline orchestrator and file scanner.

Scans raw data directory, registers files in SQLite,
dispatches to parsers, embeds chunks, and writes to ChromaDB.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable

from db_builder.database import DatabaseManager
from db_builder.embedding.client import EmbeddingClient
from db_builder.embedding.embedder import BatchEmbedder, BatchProgress
from db_builder.filetype import detect_source_type, is_supported, detect_mime, SUPPORTED_EXTENSIONS
from db_builder.parsers.base import get_parser_for_extension
from db_builder.store.chromadb_writer import ChromaDBWriter, ChunkRecord

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class FileScanner:
    """Scans a directory for supported files and registers them in the database."""

    def __init__(self, raw_data_dir: Path, db: DatabaseManager):
        self.raw_data_dir = raw_data_dir
        self.db = db

    def scan(self) -> list[dict]:
        """Walk raw_data_dir, discover supported files, and register in DB.

        Returns list of file records (new + changed files only).
        Already-processed files with matching hash are skipped.
        """
        results: list[dict] = []

        if not self.raw_data_dir.exists():
            logger.warning("Raw data directory does not exist: %s", self.raw_data_dir)
            return results

        for file_path in sorted(self.raw_data_dir.rglob("*")):
            if not file_path.is_file():
                continue

            if not is_supported(file_path):
                logger.debug("Skipping unsupported file: %s", file_path)
                continue

            rel_path = str(file_path.relative_to(self.raw_data_dir))
            file_hash = compute_file_hash(file_path)
            file_size = file_path.stat().st_size
            source_type = detect_source_type(file_path)

            existing = self.db.get_file_by_path(rel_path)

            if existing is None:
                # New file
                file_id = self.db.insert_file(
                    file_path=rel_path,
                    file_hash=file_hash,
                    file_size=file_size,
                    source_type=source_type,
                )
                record = self.db.get_file_by_id(file_id)
                results.append(record)
                logger.info("New file registered: %s (%s)", rel_path, source_type)

            elif existing["file_hash"] != file_hash:
                # File changed since last scan
                file_id = existing["id"]
                self.db.update_file_hash(file_id, file_hash, file_size)
                self.db.update_file_status(file_id, "pending")
                # Clear old chunks for re-processing
                deleted = self.db.delete_chunks_by_file(file_id)
                if deleted > 0:
                    logger.info("Cleared %d old chunks for changed file: %s", deleted, rel_path)
                record = self.db.get_file_by_id(file_id)
                results.append(record)
                logger.info("File changed, re-queued: %s", rel_path)

            else:
                # File unchanged — skip
                logger.debug("File unchanged, skipping: %s", rel_path)

        return results

    def get_processable_files(self) -> list[dict]:
        """Get all files with 'pending' status."""
        return self.db.list_files(status="pending")

    def has_parser(self, file_path: str) -> bool:
        """Check if a parser is registered for the given file."""
        ext = Path(file_path).suffix.lower()
        return get_parser_for_extension(ext) is not None


class EmbeddingPipeline:
    """Orchestrates: embed accepted chunks → write to ChromaDB.

    This handles the embed + store steps of the pipeline.
    Parsing and chunking are handled separately (Phase 2-3).
    """

    def __init__(
        self,
        db: DatabaseManager,
        embedding_client: EmbeddingClient,
        chromadb_writer: ChromaDBWriter,
        batch_size: int = 100,
        checkpoint_interval: int = 100,
        cost_per_million: float = 0.02,
        on_progress: Callable[[BatchProgress], None] | None = None,
    ):
        self.db = db
        self.client = embedding_client
        self.writer = chromadb_writer
        self.batch_size = batch_size
        self.checkpoint_interval = checkpoint_interval
        self.cost_per_million = cost_per_million
        self.on_progress = on_progress
        self._embedder: BatchEmbedder | None = None

    def run(self) -> BatchProgress:
        """Run the full embed + store pipeline.

        1. Embed all accepted, non-embedded chunks via BatchEmbedder
        2. Write newly embedded chunks to ChromaDB
        Returns BatchProgress with final stats.
        """
        # Step 1: Embed
        self._embedder = BatchEmbedder(
            db=self.db,
            client=self.client,
            batch_size=self.batch_size,
            checkpoint_interval=self.checkpoint_interval,
            cost_per_million_input=self.cost_per_million,
            on_progress=self.on_progress,
        )
        progress = self._embedder.run()

        # Step 2: Write embedded chunks to ChromaDB
        if progress.completed_chunks > 0:
            self._write_to_chromadb()

        return progress

    def cancel(self) -> None:
        if self._embedder:
            self._embedder.cancel()

    def _write_to_chromadb(self) -> None:
        """Write all embedded chunks (that have embeddings) to ChromaDB.

        Streams from SQLite in windows to avoid loading all chunks into RAM.
        """
        total_written = 0
        window_size = 5000
        offset = 0

        while True:
            rows = self.db.conn.execute(
                "SELECT * FROM chunks WHERE is_embedded = 1 "
                "ORDER BY id LIMIT ? OFFSET ?",
                (window_size, offset),
            ).fetchall()

            if not rows:
                break

            batch: list[dict] = []
            for row in rows:
                batch.append(dict(row))

                if len(batch) >= self.batch_size:
                    total_written += self._embed_and_write_batch(batch)
                    batch = []

            if batch:
                total_written += self._embed_and_write_batch(batch)

            offset += window_size

        if total_written:
            logger.info("Wrote %d chunks to ChromaDB", total_written)

    def _embed_and_write_batch(self, chunk_rows: list[dict]) -> int:
        """Embed a batch and write to ChromaDB. Returns count written."""
        texts = [r["text"] for r in chunk_rows]
        result = self.client.embed(texts)

        records = []
        for row, embedding in zip(chunk_rows, result.embeddings):
            metadata = {
                "chunk_type": row.get("chunk_type", "manual"),
                "source_file": row.get("source_file", ""),
                "source_type": row.get("source_type", ""),
                "tool_family": row.get("tool_family", "general"),
                "customer": row.get("customer", "generic"),
                "silo_key": row.get("silo_key", ""),
                "language": row.get("language", "en"),
                "token_count": row.get("token_count", 0),
                "quality_score": row.get("quality_score", 0.0),
                "is_safety_critical": bool(row.get("is_safety_critical", 0)),
            }
            # Optional fields
            for field in ["page_number", "sheet_name", "section_title",
                          "section_path", "document_version",
                          "cross_references", "issue_thread_id", "source_date"]:
                val = row.get(field)
                if val is not None:
                    metadata[field] = val

            records.append(ChunkRecord(
                id=row["id"],
                text=row["text"],
                embedding=embedding,
                metadata=metadata,
            ))

        return self.writer.upsert_chunks(records)
