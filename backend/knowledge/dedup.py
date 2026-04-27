"""Deduplication engine for Engram dreaming pipeline.

Light Sleep stage: detect exact and near-duplicate chunks.
- Exact duplicates: same ID (handled by upsert)
- Near duplicates: cosine similarity > threshold → flag for merge
- Type B (traces): NEVER merged

Spec reference: scaffolding-plan-v3.md Section 5.3
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from backend.knowledge.vectordb import VectorDB


@dataclass
class DedupReport:
    """Report from a dedup run."""

    collection: str = ""
    total_items: int = 0
    exact_duplicates_removed: int = 0
    near_duplicates_found: int = 0
    merged_count: int = 0
    skipped_traces: int = 0
    merge_candidates: list[tuple[str, str, float]] = field(default_factory=list)


class DedupEngine:
    """Deduplication engine for VectorDB collections."""

    NEAR_DUPLICATE_THRESHOLD = 0.92

    def __init__(self, vectordb: VectorDB):
        self._vectordb = vectordb

    async def run_light_sleep(self, collection_name: str) -> DedupReport:
        """Light Sleep: scan for duplicates in a collection.

        For 'traces' collection, only counts items (never merges).
        For other collections, detects near-duplicates by cross-querying.
        """
        report = DedupReport(collection=collection_name)
        report.total_items = self._vectordb.count(collection_name)

        # Type B traces: never merge
        if collection_name == "traces":
            report.skipped_traces = report.total_items
            return report

        # For case_records and weekly: check for near-duplicates
        # We query each item against the collection to find high-similarity pairs
        col = self._vectordb._get_collection(collection_name)

        try:
            all_items = col.get(
                limit=report.total_items,
                include=["embeddings", "documents", "metadatas"],
            )
        except Exception:
            return report

        ids = all_items.get("ids") or []
        embeddings = all_items.get("embeddings")

        if not ids or embeddings is None or len(embeddings) == 0:
            return report

        # Build normalised embedding matrix for cosine similarity via dot product.
        # No extra API calls — vectors are already stored in ChromaDB.
        emb = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        emb = emb / norms
        sim_matrix = emb @ emb.T  # shape (N, N)

        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                similarity = float(sim_matrix[i, j])
                if similarity >= self.NEAR_DUPLICATE_THRESHOLD:
                    report.near_duplicates_found += 1
                    report.merge_candidates.append((ids[i], ids[j], similarity))

        return report
