"""Knowledge graph for ZEMAS dreaming pipeline.

Builds a lightweight context graph from VectorDB chunks:
- Nodes: cases, issues, components, tools
- Edges: similarity, co-occurrence, thread links

Used in Deep Sleep to detect patterns and promote tacit knowledge.

Spec reference: scaffolding-plan-v3.md Section 5.3, 5.4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class GraphNode:
    """Node in the knowledge graph."""

    id: str
    type: str  # case, issue, component, tool, tacit
    label: str
    metadata: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """Edge in the knowledge graph."""

    source: str
    target: str
    type: str  # similar, co_occurrence, thread, tacit_link
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)


class KnowledgeGraph:
    """Lightweight knowledge graph built from VectorDB data."""

    def __init__(self):
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._adjacency: dict[str, list[str]] = defaultdict(list)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self._edges.append(edge)
        self._adjacency[edge.source].append(edge.target)
        self._adjacency[edge.target].append(edge.source)

    def get_node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    def get_neighbors(self, node_id: str) -> list[str]:
        return self._adjacency.get(node_id, [])

    def get_edges(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self._edges if e.source == node_id or e.target == node_id]

    def build_from_vectordb(self, vectordb, collections: list[str] | None = None):
        """Build graph from VectorDB collections.

        Adds nodes for each chunk and edges for high-similarity pairs.
        """
        collections = collections or ["case_records", "weekly"]

        for col_name in collections:
            col = vectordb._get_collection(col_name)
            try:
                items = col.get(limit=1000)
            except Exception:
                continue

            if not items["ids"]:
                continue

            for i, chunk_id in enumerate(items["ids"]):
                meta = (items["metadatas"][i] if items["metadatas"] else None) or {}
                self.add_node(GraphNode(
                    id=chunk_id,
                    type=meta.get("chunk_type", col_name),
                    label=meta.get("title", chunk_id),
                    metadata=meta,
                ))

                # Link by silo_key (same tool/account grouping)
                silo = meta.get("silo_key", "")
                if silo:
                    silo_node_id = f"silo:{silo}"
                    if silo_node_id not in self._nodes:
                        self.add_node(GraphNode(
                            id=silo_node_id, type="silo", label=silo,
                        ))
                    self.add_edge(GraphEdge(
                        source=chunk_id, target=silo_node_id,
                        type="belongs_to", weight=1.0,
                    ))

                # Link by issue_thread_id (weekly issue threading)
                thread_id = meta.get("issue_thread_id", "")
                if thread_id:
                    thread_node_id = f"thread:{thread_id}"
                    if thread_node_id not in self._nodes:
                        self.add_node(GraphNode(
                            id=thread_node_id, type="thread",
                            label=meta.get("title", thread_id),
                        ))
                    self.add_edge(GraphEdge(
                        source=chunk_id, target=thread_node_id,
                        type="thread", weight=1.0,
                    ))

    def to_dict(self) -> dict:
        """Export graph as JSON-serializable dict."""
        return {
            "nodes": [
                {"id": n.id, "type": n.type, "label": n.label, "metadata": n.metadata}
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "source": e.source, "target": e.target,
                    "type": e.type, "weight": e.weight, "metadata": e.metadata,
                }
                for e in self._edges
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeGraph":
        """Import graph from JSON dict."""
        graph = cls()
        for n in data.get("nodes", []):
            graph.add_node(GraphNode(
                id=n["id"], type=n["type"], label=n["label"],
                metadata=n.get("metadata", {}),
            ))
        for e in data.get("edges", []):
            graph.add_edge(GraphEdge(
                source=e["source"], target=e["target"],
                type=e["type"], weight=e.get("weight", 1.0),
                metadata=e.get("metadata", {}),
            ))
        return graph
