"""Deduplication engine for ZEMAS dreaming pipeline.

Light Sleep stage: detect exact and near-duplicate chunks.
- Exact duplicates: same ID (handled by upsert)
- Near duplicates: cosine similarity > threshold → flag for merge
- Type B (traces): NEVER merged

Spec reference: scaffolding-plan-v3.md Section 5.3
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
            all_items = col.get(limit=report.total_items)
        except Exception:
            return report

        if not all_items["ids"]:
            return report

        seen_pairs: set[tuple[str, str]] = set()

        for i, doc_id in enumerate(all_items["ids"]):
            doc = all_items["documents"][i] if all_items["documents"] else ""
            if not doc:
                continue

            # Query for similar documents
            try:
                results = col.query(
                    query_texts=[doc],
                    n_results=min(5, len(all_items["ids"])),
                )
            except Exception:
                continue

            if not results["ids"] or not results["ids"][0]:
                continue

            for j, match_id in enumerate(results["ids"][0]):
                if match_id == doc_id:
                    continue

                # Cosine distance → similarity
                distance = results["distances"][0][j] if results["distances"] else 1.0
                similarity = 1.0 - distance

                pair = tuple(sorted([doc_id, match_id]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                if similarity >= self.NEAR_DUPLICATE_THRESHOLD:
                    report.near_duplicates_found += 1
                    report.merge_candidates.append((doc_id, match_id, similarity))

        return report
