"""ChromaDB EmbeddingFunction implementations for Engram.

All Engram collections (case_records, traces, weekly, manuals) must use
the SAME embedding function so the semantic space is consistent and
DB Builder-produced chunks (which pre-compute vectors via OpenRouter
``openai/text-embedding-3-small``, 1536 dims) can be queried alongside
Engram-produced chunks.

This module provides:

- ``OpenRouterEmbeddingFunction`` — production function that calls
  OpenRouter via ``SyncOpenRouterEmbeddingClient``. Used by ``VectorDB``
  whenever no explicit function is injected.
- ``FakeEmbeddingFunction`` — deterministic 1536-dim vectors derived
  from a SHA-256 hash of the input text. Used in tests to avoid HTTP
  calls while still exercising every code path that touches embeddings.

Design note: ChromaDB's ``EmbeddingFunction`` interface is synchronous,
which is why we have a separate ``embedding_client.py`` (sync httpx) —
the rest of Engram uses async httpx for chat completions.

Both classes subclass ``chromadb.api.types.EmbeddingFunction`` so ChromaDB's
collection-config serialization treats them as first-class (non-legacy).
"""

from __future__ import annotations

import hashlib
import logging
import struct
from collections import OrderedDict
from typing import Any

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from backend.utils.embedding_client import SyncOpenRouterEmbeddingClient

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536
"""Dimension of ``openai/text-embedding-3-small``.

DB Builder hard-codes this in its config as well. If this ever changes,
both projects must be re-embedded from scratch (drop chroma_db/).
"""

_EF_NAME_OPENROUTER = "openrouter-text-embedding-3-small"
_EF_NAME_FAKE = "fake-deterministic-sha256"


class OpenRouterEmbeddingFunction(EmbeddingFunction[Documents]):
    """ChromaDB EmbeddingFunction backed by OpenRouter."""

    def __init__(
        self,
        client: SyncOpenRouterEmbeddingClient | None = None,
        model: str = "openai/text-embedding-3-small",
        max_cache_size: int = 256,
    ):
        self._client = client or SyncOpenRouterEmbeddingClient(model=model)
        self.model = model
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._max_cache_size = max_cache_size

    def __call__(self, input: Documents) -> Embeddings:
        if not input:
            return []
        texts = list(input)

        uncached_indices: list[int] = []
        uncached_texts: list[str] = []
        result_map: dict[int, list[float]] = {}

        for i, text in enumerate(texts):
            if text in self._cache:
                self._cache.move_to_end(text)
                result_map[i] = self._cache[text]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            api_result = self._client.embed(uncached_texts)
            if len(api_result.embeddings) != len(uncached_texts):
                raise RuntimeError(
                    f"Embedding count mismatch: got {len(api_result.embeddings)} "
                    f"for {len(uncached_texts)} inputs"
                )
            for idx, text, emb in zip(uncached_indices, uncached_texts, api_result.embeddings):
                if len(self._cache) >= self._max_cache_size:
                    self._cache.popitem(last=False)
                self._cache[text] = emb
                result_map[idx] = emb

        return [result_map[i] for i in range(len(texts))]

    @staticmethod
    def name() -> str:
        return _EF_NAME_OPENROUTER

    def default_space(self) -> str:
        return "cosine"

    def get_config(self) -> dict[str, Any]:
        return {"model": self.model}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "OpenRouterEmbeddingFunction":
        return OpenRouterEmbeddingFunction(
            model=config.get("model", "openai/text-embedding-3-small")
        )


class FakeEmbeddingFunction(EmbeddingFunction[Documents]):
    """Deterministic test-only embedding function.

    Generates a 1536-dim vector from SHA-256 of the input text.
    Identical texts → identical vectors; different texts → different
    vectors. Not semantically meaningful, which is the point: tests
    should not rely on real similarity structure.
    """

    def __init__(self, dim: int = EMBEDDING_DIM):
        self.dim = dim

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed_one(t) for t in input]

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        floats: list[float] = []
        seed = 0
        while len(floats) < self.dim:
            chunk = hashlib.sha256(digest + seed.to_bytes(4, "big")).digest()
            for i in range(0, len(chunk), 4):
                val = struct.unpack(">i", chunk[i : i + 4])[0]
                floats.append(val / (2**31))
                if len(floats) >= self.dim:
                    break
            seed += 1
        return floats

    @staticmethod
    def name() -> str:
        return _EF_NAME_FAKE

    def default_space(self) -> str:
        return "cosine"

    def get_config(self) -> dict[str, Any]:
        return {"dim": self.dim}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "FakeEmbeddingFunction":
        return FakeEmbeddingFunction(dim=config.get("dim", EMBEDDING_DIM))
