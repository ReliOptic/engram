"""ChromaDB writer for persisting embedded chunks.

Writes Type M chunks to the 'zemas_manuals' collection and
Type C chunks to the 'weekly' collection.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb

logger = logging.getLogger(__name__)

MANUALS_COLLECTION = "zemas_manuals"
WEEKLY_COLLECTION = "weekly"


@dataclass
class ChunkRecord:
    """A chunk ready to be written to ChromaDB."""

    id: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any]


class ChromaDBWriter:
    """Writes embedded chunks to ChromaDB collections."""

    def __init__(self, persist_dir: str | Path):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))

    @property
    def manuals(self) -> chromadb.Collection:
        return self._client.get_or_create_collection(
            name=MANUALS_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def weekly(self) -> chromadb.Collection:
        return self._client.get_or_create_collection(
            name=WEEKLY_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def get_collection(self, chunk_type: str) -> chromadb.Collection:
        """Get the appropriate collection for a chunk type."""
        if chunk_type == "weekly_report":
            return self.weekly
        return self.manuals

    def upsert_chunks(
        self,
        chunks: list[ChunkRecord],
        collection_name: str | None = None,
    ) -> int:
        """Upsert a batch of chunks. Returns count written.

        If collection_name is None, routes based on chunk metadata.chunk_type.
        """
        if not chunks:
            return 0

        # Group by collection
        by_collection: dict[str, list[ChunkRecord]] = {}
        for chunk in chunks:
            if collection_name:
                col_name = collection_name
            else:
                ct = chunk.metadata.get("chunk_type", "manual")
                col_name = WEEKLY_COLLECTION if ct == "weekly_report" else MANUALS_COLLECTION
            by_collection.setdefault(col_name, []).append(chunk)

        total = 0
        for col_name, col_chunks in by_collection.items():
            collection = self._client.get_or_create_collection(
                name=col_name,
                metadata={"hnsw:space": "cosine"},
            )
            # Clean metadata: ChromaDB only accepts str, int, float, bool
            clean_metadatas = [
                self._clean_metadata(c.metadata) for c in col_chunks
            ]

            collection.upsert(
                ids=[c.id for c in col_chunks],
                embeddings=[c.embedding for c in col_chunks],
                documents=[c.text for c in col_chunks],
                metadatas=clean_metadatas,
            )
            total += len(col_chunks)
            logger.info(
                "Upserted %d chunks to '%s' collection", len(col_chunks), col_name
            )

        return total

    def search(
        self,
        query_embedding: list[float],
        collection_name: str = MANUALS_COLLECTION,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """Search a collection by embedding vector."""
        collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(n_results, collection.count()),
        }
        if where:
            kwargs["where"] = where

        if collection.count() == 0:
            return []

        results = collection.query(**kwargs)

        output = []
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0.0,
            })
        return output

    def get_collection_stats(self, collection_name: str = MANUALS_COLLECTION) -> dict:
        """Get stats for a collection."""
        try:
            collection = self._client.get_collection(name=collection_name)
            return {
                "name": collection_name,
                "count": collection.count(),
            }
        except Exception:
            return {"name": collection_name, "count": 0}

    def delete_collection(self, collection_name: str) -> None:
        """Drop an entire collection."""
        try:
            self._client.delete_collection(name=collection_name)
            logger.info("Deleted collection '%s'", collection_name)
        except (ValueError, Exception) as e:
            if "does not exist" in str(e) or "NotFoundError" in type(e).__name__:
                logger.debug("Collection '%s' does not exist", collection_name)
            else:
                raise

    def export(self, output_dir: Path) -> None:
        """Copy the persist directory to another location (for ZEMAS deployment)."""
        output_dir = Path(output_dir)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.copytree(str(self.persist_dir), str(output_dir))
        logger.info("Exported ChromaDB to %s", output_dir)

    @staticmethod
    def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        """ChromaDB only accepts str, int, float, bool values.
        Convert lists/dicts to JSON strings, drop None values.
        """
        clean = {}
        for k, v in metadata.items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                clean[k] = v
            elif isinstance(v, (list, dict)):
                clean[k] = json.dumps(v)
            else:
                clean[k] = str(v)
        return clean
