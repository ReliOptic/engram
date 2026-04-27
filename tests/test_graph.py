"""Tests for the lightweight knowledge graph used by the dreaming pipeline.

Covers:
- Node/edge add + count + adjacency (bidirectional)
- get_node / get_neighbors / get_edges lookups
- build_from_vectordb derives silo + thread nodes/edges from chunk metadata
- to_dict / from_dict roundtrip preserves the graph exactly
- Building from an empty / unknown collection is a no-op
"""

from __future__ import annotations

import pytest

from backend.agents.orchestrator import AgentResponse
from backend.knowledge.graph import GraphEdge, GraphNode, KnowledgeGraph
from backend.knowledge.recording_policy import (
    build_type_a_chunk,
    build_type_c_chunk,
)
from backend.knowledge.vectordb import VectorDB


# --------------------------------------------------------------------------- #
# Pure data structure
# --------------------------------------------------------------------------- #

def test_add_node_and_edge_updates_counts():
    g = KnowledgeGraph()
    g.add_node(GraphNode("a", "case", "Case A"))
    g.add_node(GraphNode("b", "case", "Case B"))
    g.add_edge(GraphEdge("a", "b", "similar", weight=0.95))

    assert g.node_count == 2
    assert g.edge_count == 1


def test_adjacency_is_bidirectional():
    g = KnowledgeGraph()
    g.add_node(GraphNode("a", "case", "A"))
    g.add_node(GraphNode("b", "case", "B"))
    g.add_edge(GraphEdge("a", "b", "similar"))

    assert "b" in g.get_neighbors("a")
    assert "a" in g.get_neighbors("b")


def test_get_node_returns_none_for_missing():
    g = KnowledgeGraph()
    assert g.get_node("missing") is None
    assert g.get_neighbors("missing") == []
    assert g.get_edges("missing") == []


def test_get_edges_returns_all_incident_edges():
    g = KnowledgeGraph()
    g.add_node(GraphNode("a", "case", "A"))
    g.add_node(GraphNode("b", "case", "B"))
    g.add_node(GraphNode("c", "case", "C"))
    g.add_edge(GraphEdge("a", "b", "similar"))
    g.add_edge(GraphEdge("c", "a", "similar"))
    g.add_edge(GraphEdge("b", "c", "similar"))

    edges_for_a = g.get_edges("a")
    assert len(edges_for_a) == 2
    endpoints = {tuple(sorted([e.source, e.target])) for e in edges_for_a}
    assert ("a", "b") in endpoints
    assert ("a", "c") in endpoints


def test_add_node_with_same_id_overwrites():
    """Adding a node with an existing id replaces the prior entry."""
    g = KnowledgeGraph()
    g.add_node(GraphNode("a", "case", "Old"))
    g.add_node(GraphNode("a", "case", "New"))
    assert g.node_count == 1
    assert g.get_node("a").label == "New"


# --------------------------------------------------------------------------- #
# build_from_vectordb
# --------------------------------------------------------------------------- #

def _conv(text: str) -> list[AgentResponse]:
    return [AgentResponse("analyzer", "NEW_EVIDENCE", "d", "@You", text)]


def test_build_from_vectordb_creates_silo_links(tmp_path):
    """Each case_record gets a node + a belongs_to edge to its silo node."""
    vectordb = VectorDB(persist_dir=str(tmp_path / "chroma_graph_silo"))

    for i in range(2):
        meta = {
            "case_id": f"ClientA-{i:03d}",
            "account": "ClientA", "tool": "ProductA", "component": "Module1",
            "title": f"bug {i}", "resolution": "fix",
        }
        vectordb.upsert("case_records", build_type_a_chunk(meta, _conv(f"text {i}")))

    g = KnowledgeGraph()
    g.build_from_vectordb(vectordb, collections=["case_records"])

    # 2 case nodes + 1 silo node
    assert g.node_count == 3
    assert g.get_node("silo:ClientA_ProductA_Module1") is not None
    # 2 belongs_to edges
    belongs_to = [e for e in g._edges if e.type == "belongs_to"]
    assert len(belongs_to) == 2


def test_build_from_vectordb_creates_thread_links(tmp_path):
    """Weekly chunks with issue_thread_id get linked to a thread node."""
    vectordb = VectorDB(persist_dir=str(tmp_path / "chroma_graph_thread"))

    chunk = build_type_c_chunk({
        "cw": "CW15-2026", "account": "ClientA", "tool": "ProductA",
        "title": "Module1 SECS/GEM bug after SW upgrade",
        "fob": "FOB1", "status": "open",
    })
    vectordb.upsert("weekly", chunk)

    g = KnowledgeGraph()
    g.build_from_vectordb(vectordb, collections=["weekly"])

    thread_edges = [e for e in g._edges if e.type == "thread"]
    assert len(thread_edges) == 1
    thread_node_id = thread_edges[0].target
    assert thread_node_id.startswith("thread:")
    assert g.get_node(thread_node_id).type == "thread"


def test_build_from_vectordb_skips_empty_collection(tmp_path):
    """Empty collection contributes no nodes/edges."""
    vectordb = VectorDB(persist_dir=str(tmp_path / "chroma_graph_empty"))
    g = KnowledgeGraph()
    g.build_from_vectordb(vectordb, collections=["case_records"])
    assert g.node_count == 0
    assert g.edge_count == 0


def test_build_from_vectordb_default_collections(tmp_path):
    """Default collections are case_records + weekly (NOT traces)."""
    vectordb = VectorDB(persist_dir=str(tmp_path / "chroma_graph_default"))
    meta = {
        "case_id": "ClientA-001",
        "account": "ClientA", "tool": "ProductA", "component": "Module1",
        "title": "bug", "resolution": "fix",
    }
    vectordb.upsert("case_records", build_type_a_chunk(meta, _conv("x")))

    g = KnowledgeGraph()
    g.build_from_vectordb(vectordb)  # default
    # case + silo nodes appear; nothing from traces
    assert g.get_node("case-ClientA-001") is not None


# --------------------------------------------------------------------------- #
# Roundtrip serialisation
# --------------------------------------------------------------------------- #

def test_to_dict_from_dict_roundtrip():
    g = KnowledgeGraph()
    g.add_node(GraphNode("a", "case", "A", metadata={"k": "v"}))
    g.add_node(GraphNode("b", "case", "B"))
    g.add_edge(GraphEdge("a", "b", "similar", weight=0.8, metadata={"why": "test"}))

    data = g.to_dict()
    restored = KnowledgeGraph.from_dict(data)

    assert restored.node_count == g.node_count
    assert restored.edge_count == g.edge_count
    assert restored.get_node("a").metadata == {"k": "v"}
    edge = restored._edges[0]
    assert edge.weight == 0.8
    assert edge.metadata == {"why": "test"}
