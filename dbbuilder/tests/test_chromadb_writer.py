"""Tests for ChromaDB writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from db_builder.store.chromadb_writer import (
    MANUALS_COLLECTION,
    WEEKLY_COLLECTION,
    ChromaDBWriter,
    ChunkRecord,
)


@pytest.fixture
def writer(tmp_path: Path) -> ChromaDBWriter:
    return ChromaDBWriter(persist_dir=tmp_path / "chroma_test")


def _make_chunk(
    chunk_id: str = "m-abc_p01_001",
    text: str = "System calibration procedure for ProductA system.",
    tool_family: str = "ProductA",
    chunk_type: str = "manual",
) -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id,
        text=text,
        embedding=[0.1, 0.2, 0.3] * 512,  # 1536 dims
        metadata={
            "chunk_type": chunk_type,
            "source_file": "sample_manual.pdf",
            "tool_family": tool_family,
            "page_number": 42,
            "section_title": "Chapter 8 > 8.3 System Recalibration",
            "language": "en",
            "quality_score": 0.87,
            "is_safety_critical": False,
            "token_count": 150,
        },
    )


class TestUpsert:
    def test_upsert_single(self, writer: ChromaDBWriter):
        chunk = _make_chunk()
        count = writer.upsert_chunks([chunk])
        assert count == 1
        assert writer.manuals.count() == 1

    def test_upsert_batch(self, writer: ChromaDBWriter):
        chunks = [
            _make_chunk(f"chunk-{i}", f"Text {i}")
            for i in range(5)
        ]
        count = writer.upsert_chunks(chunks)
        assert count == 5
        assert writer.manuals.count() == 5

    def test_upsert_empty(self, writer: ChromaDBWriter):
        count = writer.upsert_chunks([])
        assert count == 0

    def test_upsert_idempotent(self, writer: ChromaDBWriter):
        """Same ID → overwrites, no duplicate."""
        chunk = _make_chunk("same-id", "original text")
        writer.upsert_chunks([chunk])
        assert writer.manuals.count() == 1

        updated = _make_chunk("same-id", "updated text")
        writer.upsert_chunks([updated])
        assert writer.manuals.count() == 1

        # Verify content was updated
        result = writer.manuals.get(ids=["same-id"])
        assert result["documents"][0] == "updated text"

    def test_routes_weekly_to_correct_collection(self, writer: ChromaDBWriter):
        manual_chunk = _make_chunk("m-001", chunk_type="manual")
        weekly_chunk = _make_chunk("w-001", chunk_type="weekly_report")
        weekly_chunk.metadata["chunk_type"] = "weekly_report"

        writer.upsert_chunks([manual_chunk, weekly_chunk])

        assert writer.manuals.count() == 1
        assert writer.weekly.count() == 1

    def test_metadata_cleaned(self, writer: ChromaDBWriter):
        """Lists and None values are handled correctly."""
        chunk = ChunkRecord(
            id="meta-test",
            text="test",
            embedding=[0.1] * 1536,
            metadata={
                "chunk_type": "manual",
                "cross_references": ["Chapter 1", "Chapter 2"],
                "section_path": ["Ch 8", "8.3"],
                "optional_field": None,
                "score": 0.87,
                "is_critical": True,
            },
        )
        writer.upsert_chunks([chunk])

        result = writer.manuals.get(ids=["meta-test"], include=["metadatas"])
        meta = result["metadatas"][0]
        # Lists should be JSON strings
        assert meta["cross_references"] == '["Chapter 1", "Chapter 2"]'
        assert meta["section_path"] == '["Ch 8", "8.3"]'
        # None should be dropped
        assert "optional_field" not in meta
        # Primitives preserved
        assert meta["score"] == 0.87
        assert meta["is_critical"] is True


class TestSearch:
    def test_search_returns_results(self, writer: ChromaDBWriter):
        chunks = [
            _make_chunk("c1", "System calibration procedure step 4", "ProductA"),
            _make_chunk("c2", "ProductB detector alignment procedure", "ProductB"),
            _make_chunk("c3", "ProductA stage leveling check", "ProductA"),
        ]
        writer.upsert_chunks(chunks)

        # Search with same-ish embedding
        results = writer.search(
            query_embedding=[0.1, 0.2, 0.3] * 512,
            n_results=3,
        )
        assert len(results) == 3
        assert all("id" in r for r in results)
        assert all("document" in r for r in results)
        assert all("distance" in r for r in results)

    def test_search_with_filter(self, writer: ChromaDBWriter):
        chunks = [
            _make_chunk("c1", "ProductA manual content", "ProductA"),
            _make_chunk("c2", "ProductB manual content", "ProductB"),
        ]
        writer.upsert_chunks(chunks)

        results = writer.search(
            query_embedding=[0.1, 0.2, 0.3] * 512,
            where={"tool_family": "ProductA"},
            n_results=5,
        )
        assert len(results) == 1
        assert results[0]["metadata"]["tool_family"] == "ProductA"

    def test_search_empty_collection(self, writer: ChromaDBWriter):
        results = writer.search(
            query_embedding=[0.1] * 1536,
            n_results=5,
        )
        assert results == []

    def test_search_weekly_collection(self, writer: ChromaDBWriter):
        chunk = _make_chunk("w1", "weekly report content", chunk_type="weekly_report")
        chunk.metadata["chunk_type"] = "weekly_report"
        writer.upsert_chunks([chunk])

        results = writer.search(
            query_embedding=[0.1, 0.2, 0.3] * 512,
            collection_name=WEEKLY_COLLECTION,
            n_results=5,
        )
        assert len(results) == 1


class TestDeterministicIds:
    def test_same_source_same_id(self, writer: ChromaDBWriter):
        """Rebuild safety: same file produces same IDs."""
        import hashlib
        source = "sample_manual.pdf"
        file_hash = hashlib.md5(source.encode()).hexdigest()[:6]
        chunk_id = f"m-{file_hash}_p042_002"

        # First build
        c1 = _make_chunk(chunk_id, "original")
        writer.upsert_chunks([c1])

        # Second build (rebuild)
        c2 = _make_chunk(chunk_id, "rebuilt")
        writer.upsert_chunks([c2])

        assert writer.manuals.count() == 1
        result = writer.manuals.get(ids=[chunk_id])
        assert result["documents"][0] == "rebuilt"


class TestCollectionManagement:
    def test_get_stats(self, writer: ChromaDBWriter):
        writer.upsert_chunks([_make_chunk("c1")])
        stats = writer.get_collection_stats(MANUALS_COLLECTION)
        assert stats["name"] == MANUALS_COLLECTION
        assert stats["count"] == 1

    def test_get_stats_nonexistent(self, writer: ChromaDBWriter):
        stats = writer.get_collection_stats("nonexistent")
        assert stats["count"] == 0

    def test_delete_collection(self, writer: ChromaDBWriter):
        writer.upsert_chunks([_make_chunk("c1")])
        assert writer.manuals.count() == 1

        writer.delete_collection(MANUALS_COLLECTION)
        stats = writer.get_collection_stats(MANUALS_COLLECTION)
        assert stats["count"] == 0

    def test_delete_nonexistent(self, writer: ChromaDBWriter):
        # Should not raise
        writer.delete_collection("nonexistent_collection")

    def test_export(self, writer: ChromaDBWriter, tmp_path: Path):
        writer.upsert_chunks([_make_chunk("c1")])

        export_dir = tmp_path / "export"
        writer.export(export_dir)

        assert export_dir.exists()
        # Verify we can open the exported DB
        exported = ChromaDBWriter(export_dir)
        stats = exported.get_collection_stats(MANUALS_COLLECTION)
        assert stats["count"] == 1
