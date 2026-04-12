"""Dreaming pipeline — nightly knowledge consolidation.

Three sleep stages:
1. Light Sleep: Deduplication — remove exact/near-duplicate chunks
2. REM Sleep: Pattern detection — find recurring issues, tacit signals
3. Deep Sleep: Graph consolidation — merge patterns into knowledge graph

Spec reference: scaffolding-plan-v3.md Section 5.3
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.knowledge.dedup import DedupEngine, DedupReport
from backend.knowledge.graph import KnowledgeGraph
from backend.knowledge.vectordb import VectorDB


@dataclass
class DreamingReport:
    """Report from a full dreaming cycle."""

    timestamp: str = ""
    light_sleep: list[DedupReport] = field(default_factory=list)
    rem_patterns: list[dict] = field(default_factory=list)
    deep_graph_nodes: int = 0
    deep_graph_edges: int = 0


class DreamingPipeline:
    """Nightly dreaming pipeline for knowledge consolidation."""

    def __init__(self, vectordb: VectorDB):
        self._vectordb = vectordb
        self._dedup = DedupEngine(vectordb)
        self._graph = KnowledgeGraph()

    async def run_full_cycle(self) -> DreamingReport:
        """Run all three sleep stages sequentially.

        Returns a DreamingReport with results from each stage.
        """
        report = DreamingReport(
            timestamp=datetime.now(tz=UTC).isoformat(),
        )

        # 1. Light Sleep: Deduplication
        for collection in ["case_records", "weekly", "traces"]:
            dedup_report = await self._dedup.run_light_sleep(collection)
            report.light_sleep.append(dedup_report)

        # 2. REM Sleep: Pattern detection
        report.rem_patterns = await self._run_rem_sleep()

        # 3. Deep Sleep: Graph consolidation
        await self._run_deep_sleep()
        report.deep_graph_nodes = self._graph.node_count
        report.deep_graph_edges = self._graph.edge_count

        return report

    async def _run_rem_sleep(self) -> list[dict]:
        """REM Sleep: Detect recurring patterns in tacit signals.

        Scans Type B chunks for tacit_signals metadata.
        Groups by type and identifies signals that appear 3+ times.
        """
        patterns = []
        col = self._vectordb._get_collection("traces")

        try:
            items = col.get(limit=1000)
        except Exception:
            return patterns

        if not items["ids"]:
            return patterns

        # Collect all tacit signals
        signal_groups: dict[str, list[dict]] = {}
        for i, _ in enumerate(items["ids"]):
            meta = items["metadatas"][i] if items["metadatas"] else {}
            tacit_raw = meta.get("tacit_signals", "")
            if not tacit_raw:
                continue

            try:
                signals = json.loads(tacit_raw) if isinstance(tacit_raw, str) else tacit_raw
            except (json.JSONDecodeError, TypeError):
                continue

            if not isinstance(signals, list):
                continue

            for sig in signals:
                sig_type = sig.get("type", "unknown")
                if sig_type not in signal_groups:
                    signal_groups[sig_type] = []
                signal_groups[sig_type].append(sig)

        # Detect recurring patterns (3+ occurrences of same type)
        for sig_type, signals in signal_groups.items():
            if len(signals) >= 3:
                patterns.append({
                    "type": sig_type,
                    "count": len(signals),
                    "signals": signals[:5],  # Top 5 examples
                    "promotion_candidate": True,
                })
            elif len(signals) >= 1:
                patterns.append({
                    "type": sig_type,
                    "count": len(signals),
                    "signals": signals,
                    "promotion_candidate": False,
                })

        return patterns

    async def _run_deep_sleep(self) -> None:
        """Deep Sleep: Build/update knowledge graph from VectorDB data."""
        self._graph = KnowledgeGraph()
        self._graph.build_from_vectordb(self._vectordb)

    def export_graph(self) -> dict:
        """Export current knowledge graph as JSON."""
        return self._graph.to_dict()

    def import_graph(self, data: dict) -> None:
        """Import knowledge graph from JSON, with conflict detection."""
        imported = KnowledgeGraph.from_dict(data)

        # Merge: add nodes/edges that don't exist yet
        for node_id, node in imported._nodes.items():
            if node_id not in self._graph._nodes:
                self._graph.add_node(node)

        existing_pairs = {
            (e.source, e.target, e.type) for e in self._graph._edges
        }
        for edge in imported._edges:
            key = (edge.source, edge.target, edge.type)
            if key not in existing_pairs:
                self._graph.add_edge(edge)
