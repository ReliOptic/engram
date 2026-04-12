"""Tests for manuals collection cross-project integration.

Verifies that Engram's VectorDB can correctly query the manuals
collection produced by DB Builder. The key risk this test guards
against is a silent embedding-dimension mismatch (which used to be
swallowed by a bare ``except`` in ``VectorDB.search``).

Spec reference: scaffolding-plan-v3.md Section 5.1 (Manuals)
"""

from __future__ import annotations

import pytest

from backend.knowledge.embedding_function import (
    EMBEDDING_DIM,
    FakeEmbeddingFunction,
)
from backend.knowledge.vectordb import VectorDB
from backend.memory.preloader import SessionPreloader


@pytest.fixture
def vectordb(tmp_path):
    """Fresh VectorDB with FakeEmbeddingFunction (autouse fixture already
    patches the default factory; this fixture just exercises the DI path)."""
    return VectorDB(
        persist_dir=str(tmp_path / "chroma_manuals_test"),
        embedding_function=FakeEmbeddingFunction(),
    )


def _manual_chunk(
    chunk_id: str,
    text: str,
    *,
    tool_family: str = "ProductA",
    source_file: str = "ProductA_manual_v3.pdf",
    page_number: int = 42,
    section_title: str = "Chapter 8 > 8.3 TIS Recalibration",
) -> dict:
    """Build a chunk shaped exactly like DB Builder would emit (see
    ``db_builder/ui/build_panel.py`` and ``db_builder/pipeline.py``)."""
    return {
        "id": chunk_id,
        "document": text,
        "metadata": {
            "chunk_type": "manual",
            "source_file": source_file,
            "source_type": "manual",
            "tool_family": tool_family,
            "customer": "generic",
            "silo_key": "",
            "language": "en",
            "token_count": len(text.split()),
            "quality_score": 0.87,
            "is_safety_critical": False,
            "page_number": page_number,
            "section_title": section_title,
        },
    }


class TestManualsCollection:
    def test_upsert_and_search(self, vectordb: VectorDB):
        """Basic write-then-read works for manuals."""
        vectordb.upsert(
            "manuals",
            _manual_chunk("m-001", "TIS recalibration procedure for ProductA step 4"),
        )
        results = vectordb.search("manuals", "TIS recalibration", n_results=5)
        assert len(results) == 1
        assert results[0]["id"] == "m-001"

    def test_tool_family_filter(self, vectordb: VectorDB):
        """Engram preloader filters manuals via ``where={'tool_family': tool}``.
        If this ever stops working, every Engram session pre-load will
        silently return zero manual hits."""
        vectordb.upsert_batch(
            "manuals",
            [
                _manual_chunk("m-p1", "ProductA calibration", tool_family="ProductA"),
                _manual_chunk("m-p2", "ProductA stage alignment", tool_family="ProductA"),
                _manual_chunk("m-a1", "ProductB detector alignment", tool_family="ProductB"),
            ],
        )
        prove_results = vectordb.search(
            "manuals", "calibration",
            where={"tool_family": "ProductA"},
            n_results=10,
        )
        assert len(prove_results) == 2
        assert all(r["metadata"]["tool_family"] == "ProductA" for r in prove_results)

    def test_embedding_dimension_is_1536(self, vectordb: VectorDB):
        """The whole integration rests on everyone agreeing on 1536 dims.

        This test exists so that if someone accidentally swaps embedding
        models (e.g., switches to MiniLM or a custom model), CI catches
        it before DB Builder and Engram silently diverge in production."""
        fake = FakeEmbeddingFunction()
        vec = fake(["hello world"])[0]
        assert len(vec) == EMBEDDING_DIM == 1536


class TestPreloaderManuals:
    async def test_preloader_surfaces_manuals(self, vectordb: VectorDB):
        """End-to-end: preloader.build_context picks up manuals hits.

        This is the exact path Engram sessions use — if it returns an
        empty list, the finder/reviewer agents lose access to manuals."""
        vectordb.upsert_batch(
            "manuals",
            [
                _manual_chunk("m-1", "ProductA TIS recalibration procedure",
                              tool_family="ProductA"),
                _manual_chunk("m-2", "ProductA stage leveling check",
                              tool_family="ProductA"),
                _manual_chunk("m-3", "ProductB detector alignment guide",
                              tool_family="ProductB"),
            ],
        )

        preloader = SessionPreloader(vectordb)
        ctx = await preloader.build_context(
            account="ClientA",
            tool="ProductA",
            component="Module1",
            query="TIS recalibration",
            max_manuals=5,
        )

        # All ProductA manuals should come back, no ProductB
        assert len(ctx.manual_entries) == 2
        tool_families = {m["metadata"]["tool_family"] for m in ctx.manual_entries}
        assert tool_families == {"ProductA"}

    async def test_preloader_manuals_empty_when_no_match(self, vectordb: VectorDB):
        """No ProductA manuals — manual_entries stays empty, no crash."""
        vectordb.upsert(
            "manuals",
            _manual_chunk("m-a1", "ProductB detector guide", tool_family="ProductB"),
        )
        preloader = SessionPreloader(vectordb)
        ctx = await preloader.build_context(
            account="ClientA",
            tool="ProductA",
            component="Module1",
            query="anything",
            max_manuals=5,
        )
        assert ctx.manual_entries == []
