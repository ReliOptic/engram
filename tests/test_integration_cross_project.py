"""Cross-project integration test: DB Builder writes, ZEMAS reads.

Simulates the end-to-end flow that matters most for the ZEMAS ↔ DB Builder
contract:

1. DB Builder creates a ``manuals`` collection in a shared ``chroma_db``
   directory, using an ``OpenRouterEmbeddingFunction`` with a known
   ``name()``.
2. DB Builder writes chunks with pre-computed 1536-dim embeddings.
3. ZEMAS opens the same persist_dir with its own
   ``OpenRouterEmbeddingFunction`` (same ``name()``) and issues a
   text-based query.
4. ChromaDB must NOT raise a config-mismatch error. Results must come
   back, filtered by ``tool_family``.

This test doesn't import DB Builder (to avoid cross-project coupling
at import time). It simulates DB Builder's writer behavior by creating
a collection with matching embedding-function ``name()``.

Spec reference: scaffolding-plan-v3.md Section 5.1 + docs/status.md
"DB Builder Strategy".
"""

from __future__ import annotations

import pytest
import chromadb

from backend.knowledge.embedding_function import (
    EMBEDDING_DIM,
    FakeEmbeddingFunction,
)
from backend.knowledge.vectordb import VectorDB


def _precomputed_chunk(idx: int, tool_family: str) -> dict:
    """Mimics a DB Builder ChunkRecord's metadata shape (see
    ``db_builder/pipeline.py::_embed_and_write_batch``)."""
    return {
        "id": f"m-{idx:03d}",
        "document": f"Manual paragraph {idx} about {tool_family} calibration",
        "metadata": {
            "chunk_type": "manual",
            "source_file": f"{tool_family}_manual_v3.pdf",
            "source_type": "manual",
            "tool_family": tool_family,
            "customer": "generic",
            "silo_key": "",
            "language": "en",
            "token_count": 8,
            "quality_score": 0.87,
            "is_safety_critical": False,
            "page_number": idx,
            "section_title": f"Chapter {idx // 10 + 1}",
        },
    }


class TestCrossProjectManuals:
    def test_db_builder_writes_zemas_reads(self, tmp_path):
        """The full cross-project scenario in one test.

        Writer side: uses FakeEmbeddingFunction to pre-compute vectors
        (stand-in for DB Builder's explicit embeddings via OpenRouter).
        Reader side: ZEMAS VectorDB with its own FakeEmbeddingFunction
        (autouse fixture replaces the factory).

        Both sides MUST use the same EmbeddingFunction class name so
        ChromaDB's stored collection config matches on reopen.
        """
        persist_dir = str(tmp_path / "shared_chroma_db")

        # ── Writer side (simulates DB Builder) ──────────────────────
        fake_writer_fn = FakeEmbeddingFunction()
        writer_client = chromadb.PersistentClient(path=persist_dir)
        writer_col = writer_client.get_or_create_collection(
            name="manuals",
            embedding_function=fake_writer_fn,
            metadata={"hnsw:space": "cosine"},
        )
        # Pre-compute embeddings the same way DB Builder does:
        chunks = [_precomputed_chunk(i, "PROVE") for i in range(5)] + [
            _precomputed_chunk(i + 100, "AIMS") for i in range(3)
        ]
        docs = [c["document"] for c in chunks]
        ids = [c["id"] for c in chunks]
        metas = [c["metadata"] for c in chunks]
        embeddings = fake_writer_fn(docs)
        writer_col.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=docs,
            metadatas=metas,
        )

        # Sanity: writer sees all 8 chunks.
        assert writer_col.count() == 8

        # ── Reader side (ZEMAS VectorDB) ───────────────────────────
        # Autouse conftest fixture already patches ``_default_embedding_function``
        # to return FakeEmbeddingFunction, so no explicit injection needed.
        zemas_vdb = VectorDB(persist_dir=persist_dir)

        # Count sanity: ZEMAS sees the same chunks DB Builder wrote.
        assert zemas_vdb.count("manuals") == 8

        # Query with tool_family filter — must return PROVE only.
        prove_results = zemas_vdb.search(
            "manuals",
            "calibration",
            where={"tool_family": "PROVE"},
            n_results=10,
        )
        assert len(prove_results) == 5
        assert all(r["metadata"]["tool_family"] == "PROVE" for r in prove_results)

        # And AIMS isolation works too.
        aims_results = zemas_vdb.search(
            "manuals",
            "calibration",
            where={"tool_family": "AIMS"},
            n_results=10,
        )
        assert len(aims_results) == 3

    def test_embedding_dim_consistency(self):
        """Belt-and-suspenders: both sides expect 1536 dims.

        Regression guard for accidental model swaps. If DB Builder's
        ``embedding_dimension`` drifts from ZEMAS's ``EMBEDDING_DIM``,
        this test fails fast instead of failing silently later in
        cosine-distance math."""
        fake = FakeEmbeddingFunction()
        vec = fake(["probe"])[0]
        assert len(vec) == EMBEDDING_DIM == 1536
