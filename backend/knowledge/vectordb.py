"""ChromaDB wrapper for Engram knowledge base.

Manages collections for different chunk types:
- case_records (Type A): LLM-structured case summaries
- traces (Type B): Raw conversation traces, never merged
- weekly (Type C): Parsed weekly report rows
- manuals (Type D): Manual/wiki chunks (created by DB Builder)

All collections share a single ``EmbeddingFunction`` so the semantic
space is consistent and DB Builder-produced manuals can be queried
alongside Engram-produced case_records / traces / weekly chunks.

Shared between Engram and DB Builder.
Spec reference: scaffolding-plan-v3.md Section 5.1
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from typing import Any

import chromadb

from backend.knowledge.embedding_function import OpenRouterEmbeddingFunction

logger = logging.getLogger(__name__)

# ChromaDB requires non-empty metadata dicts and only supports flat scalar values.
_EMPTY_METADATA = {"_": "1"}


def _ensure_metadata(metadata: dict | None) -> dict:
    """Ensure metadata is a non-empty dict with flat scalar values only."""
    if not metadata:
        return dict(_EMPTY_METADATA)
    return metadata

# Known collections
COLLECTIONS = ("case_records", "traces", "weekly", "manuals")


def _default_embedding_function():
    """Factory for the default embedding function.

    Patched by tests (see ``tests/conftest.py``) to return
    ``FakeEmbeddingFunction`` — do not inline this or tests will
    start hitting real OpenRouter.
    """
    return OpenRouterEmbeddingFunction()


class VectorDB:
    """ChromaDB wrapper with collection management and silo-based filtering."""

    def __init__(
        self,
        persist_dir: str | None = None,
        embedding_function: Any | None = None,
    ):
        if persist_dir:
            self._client = chromadb.PersistentClient(path=persist_dir)
        else:
            self._client = chromadb.Client()

        self._embedding_function = embedding_function or _default_embedding_function()
        self._collections: dict[str, Any] = {}
        self._collections_lock = threading.Lock()

    def _get_collection(self, name: str):
        """Get or create a collection with the shared embedding function."""
        if name not in self._collections:
            with self._collections_lock:
                if name not in self._collections:
                    self._collections[name] = self._client.get_or_create_collection(
                        name=name,
                        embedding_function=self._embedding_function,
                        metadata={"hnsw:space": "cosine"},
                    )
        return self._collections[name]

    def add(self, collection_name: str, chunk: dict) -> str:
        """Add a single chunk to a collection.

        Args:
            collection_name: One of COLLECTIONS.
            chunk: Dict with keys: id, document, metadata.

        Returns:
            The chunk ID.
        """
        col = self._get_collection(collection_name)
        chunk_id = chunk.get("id") or self._generate_id(chunk["document"])

        col.add(
            ids=[chunk_id],
            documents=[chunk["document"]],
            metadatas=[_ensure_metadata(chunk.get("metadata"))],
        )
        return chunk_id

    def upsert(self, collection_name: str, chunk: dict) -> str:
        """Upsert a chunk (insert or update if ID exists).

        Args:
            collection_name: One of COLLECTIONS.
            chunk: Dict with keys: id, document, metadata.

        Returns:
            The chunk ID.
        """
        col = self._get_collection(collection_name)
        chunk_id = chunk.get("id") or self._generate_id(chunk["document"])

        col.upsert(
            ids=[chunk_id],
            documents=[chunk["document"]],
            metadatas=[_ensure_metadata(chunk.get("metadata"))],
        )
        return chunk_id

    def upsert_batch(self, collection_name: str, chunks: list[dict]) -> list[str]:
        """Upsert multiple chunks at once.

        Args:
            collection_name: One of COLLECTIONS.
            chunks: List of chunk dicts.

        Returns:
            List of chunk IDs.
        """
        if not chunks:
            return []

        col = self._get_collection(collection_name)

        # Deduplicate within batch — keep last occurrence of each ID
        seen: dict[str, int] = {}
        for i, c in enumerate(chunks):
            chunk_id = c.get("id") or self._generate_id(c["document"])
            seen[chunk_id] = i
        unique_indices = sorted(seen.values())
        chunks = [chunks[i] for i in unique_indices]

        ids = [c.get("id") or self._generate_id(c["document"]) for c in chunks]
        documents = [c["document"] for c in chunks]
        metadatas = [_ensure_metadata(c.get("metadata")) for c in chunks]

        col.upsert(ids=ids, documents=documents, metadatas=metadatas)
        return ids

    def search(
        self,
        collection_name: str,
        query: str,
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[dict]:
        """Similarity search with optional metadata filter.

        Args:
            collection_name: Collection to search.
            query: Query text.
            n_results: Max results to return.
            where: ChromaDB metadata filter (e.g., {"account": "ClientA"}).

        Returns:
            List of dicts with keys: id, document, metadata, distance.
            Returns [] if the collection is empty or missing.
        """
        col = self._get_collection(collection_name)

        count = col.count()
        if count == 0:
            return []

        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results, count),
        }
        if where:
            kwargs["where"] = where

        # Let errors surface — silently returning [] hides dimension
        # mismatches, missing embedding functions, and malformed filters.
        # Callers that genuinely want tolerance should wrap this themselves.
        results = col.query(**kwargs)

        items = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                meta = (results["metadatas"][0][i] if results["metadatas"] else None) or {}
                items.append({
                    "id": doc_id,
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": meta,
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                })
        return items

    def search_by_silo(
        self,
        collection_name: str,
        query: str,
        account: str,
        tool: str,
        component: str | None = None,
        n_results: int = 10,
    ) -> list[dict]:
        """Search within a specific silo (account_tool_component).

        Args:
            collection_name: Collection to search.
            query: Query text.
            account: Account name (e.g., "Client A").
            tool: Tool name (e.g., "Product A").
            component: Optional component filter (e.g., "Module 1").
            n_results: Max results.

        Returns:
            Filtered search results.
        """
        if component:
            silo_key = f"{account}_{tool}_{component}"
            where = {"silo_key": silo_key}
        else:
            where = {"$and": [{"account": account}, {"tool": tool}]}

        return self.search(collection_name, query, n_results=n_results, where=where)

    def get_by_id(self, collection_name: str, chunk_id: str) -> dict | None:
        """Get a specific chunk by ID."""
        col = self._get_collection(collection_name)
        try:
            result = col.get(ids=[chunk_id])
            if result["ids"]:
                meta = (result["metadatas"][0] if result["metadatas"] else None) or {}
                return {
                    "id": result["ids"][0],
                    "document": result["documents"][0] if result["documents"] else "",
                    "metadata": meta,
                }
        except Exception:
            pass
        return None

    def update_metadata(self, collection_name: str, chunk_id: str, metadata: dict) -> None:
        """Update metadata fields on an existing chunk."""
        col = self._get_collection(collection_name)
        col.update(ids=[chunk_id], metadatas=[metadata])

    def count(self, collection_name: str) -> int:
        """Get the number of items in a collection."""
        col = self._get_collection(collection_name)
        return col.count()

    async def async_search(
        self,
        collection_name: str,
        query: str,
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[dict]:
        """Non-blocking wrapper around search() for use in async contexts."""
        return await asyncio.to_thread(self.search, collection_name, query, n_results, where)

    async def async_search_by_silo(
        self,
        collection_name: str,
        query: str,
        account: str,
        tool: str,
        component: str | None = None,
        n_results: int = 10,
    ) -> list[dict]:
        """Non-blocking wrapper around search_by_silo() for use in async contexts."""
        return await asyncio.to_thread(
            self.search_by_silo, collection_name, query, account, tool, component, n_results
        )

    @staticmethod
    def _generate_id(text: str) -> str:
        """Generate deterministic ID from document text."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]
