"""Tests for KnowledgeGraph — node/edge ops, serialization, VectorDB build."""

import pytest

from backend.knowledge.graph import GraphEdge, GraphNode, KnowledgeGraph


# ---------------------------------------------------------------------------
# Node operations
# ---------------------------------------------------------------------------

def test_add_and_get_node():
    graph = KnowledgeGraph()
    node = GraphNode(id="case-001", type="case", label="PRV-4412")
    graph.add_node(node)
    assert graph.get_node("case-001") is node


def test_get_nonexistent_node_returns_none():
    assert KnowledgeGraph().get_node("missing") is None


def test_node_count_starts_at_zero():
    assert KnowledgeGraph().node_count == 0


def test_node_count_increments():
    graph = KnowledgeGraph()
    graph.add_node(GraphNode(id="n1", type="case", label="A"))
    graph.add_node(GraphNode(id="n2", type="tool", label="B"))
    assert graph.node_count == 2


def test_add_node_overwrites_duplicate_id():
    graph = KnowledgeGraph()
    graph.add_node(GraphNode(id="n1", type="case", label="Original"))
    graph.add_node(GraphNode(id="n1", type="case", label="Updated"))
    assert graph.node_count == 1
    assert graph.get_node("n1").label == "Updated"


# ---------------------------------------------------------------------------
# Edge operations
# ---------------------------------------------------------------------------

def test_edge_count_starts_at_zero():
    assert KnowledgeGraph().edge_count == 0


def test_add_edge_increments_edge_count():
    graph = KnowledgeGraph()
    graph.add_edge(GraphEdge(source="a", target="b", type="similar"))
    assert graph.edge_count == 1


def test_get_edges_returns_edges_for_node():
    graph = KnowledgeGraph()
    graph.add_edge(GraphEdge(source="a", target="b", type="similar", weight=0.9))
    edges = graph.get_edges("a")
    assert len(edges) == 1
    assert edges[0].type == "similar"
    assert edges[0].weight == pytest.approx(0.9)


def test_get_edges_returns_edges_where_node_is_target():
    graph = KnowledgeGraph()
    graph.add_edge(GraphEdge(source="a", target="b", type="thread"))
    edges = graph.get_edges("b")
    assert len(edges) == 1


def test_get_neighbors_bidirectional():
    graph = KnowledgeGraph()
    graph.add_edge(GraphEdge(source="a", target="b", type="co_occurrence"))
    assert "b" in graph.get_neighbors("a")
    assert "a" in graph.get_neighbors("b")


def test_get_neighbors_no_edges_returns_empty_list():
    graph = KnowledgeGraph()
    graph.add_node(GraphNode(id="isolated", type="case", label="X"))
    assert graph.get_neighbors("isolated") == []


def test_get_neighbors_unknown_node_returns_empty_list():
    assert KnowledgeGraph().get_neighbors("ghost") == []


# ---------------------------------------------------------------------------
# Serialization — to_dict / from_dict round-trip
# ---------------------------------------------------------------------------

def test_to_dict_from_dict_preserves_nodes_and_edges():
    graph = KnowledgeGraph()
    graph.add_node(GraphNode(id="n1", type="case", label="PRV", metadata={"account": "ClientA"}))
    graph.add_node(GraphNode(id="silo:ClientA_ProductA", type="silo", label="ClientA_ProductA"))
    graph.add_edge(GraphEdge(source="n1", target="silo:ClientA_ProductA", type="belongs_to", weight=1.0))

    data = graph.to_dict()
    restored = KnowledgeGraph.from_dict(data)

    assert restored.node_count == graph.node_count
    assert restored.edge_count == graph.edge_count
    assert restored.get_node("n1").label == "PRV"
    assert restored.get_node("n1").metadata["account"] == "ClientA"


def test_to_dict_structure():
    graph = KnowledgeGraph()
    data = graph.to_dict()
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)


def test_from_dict_empty_returns_empty_graph():
    graph = KnowledgeGraph.from_dict({"nodes": [], "edges": []})
    assert graph.node_count == 0
    assert graph.edge_count == 0


def test_from_dict_missing_keys_returns_empty_graph():
    graph = KnowledgeGraph.from_dict({})
    assert graph.node_count == 0
    assert graph.edge_count == 0


def test_round_trip_preserves_edge_weight():
    graph = KnowledgeGraph()
    graph.add_edge(GraphEdge(source="x", target="y", type="similar", weight=0.75))
    restored = KnowledgeGraph.from_dict(graph.to_dict())
    assert restored._edges[0].weight == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# build_from_vectordb
# ---------------------------------------------------------------------------

def test_build_from_vectordb_creates_chunk_nodes(tmp_path):
    from backend.knowledge.vectordb import VectorDB

    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_graph_build"))
    vdb.add("case_records", {
        "id": "case-001",
        "document": "PRV offset after PM",
        "metadata": {"account": "ClientA", "tool": "ProductA", "silo_key": "ClientA_ProductA_M1"},
    })
    vdb.add("case_records", {
        "id": "case-002",
        "document": "Valve pressure drop",
        "metadata": {"account": "ClientA", "tool": "ProductA", "silo_key": "ClientA_ProductA_M2"},
    })

    graph = KnowledgeGraph()
    graph.build_from_vectordb(vdb, collections=["case_records"])

    assert graph.get_node("case-001") is not None
    assert graph.get_node("case-002") is not None


def test_build_from_vectordb_creates_silo_edges(tmp_path):
    from backend.knowledge.vectordb import VectorDB

    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_graph_silo"))
    vdb.add("case_records", {
        "id": "case-001",
        "document": "Test case document",
        "metadata": {"silo_key": "ClientA_ProductA_Module1"},
    })

    graph = KnowledgeGraph()
    graph.build_from_vectordb(vdb, collections=["case_records"])

    assert "silo:ClientA_ProductA_Module1" in graph.get_neighbors("case-001")


def test_build_from_vectordb_two_chunks_same_silo_share_silo_node(tmp_path):
    from backend.knowledge.vectordb import VectorDB

    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_graph_shared_silo"))
    for i in range(3):
        vdb.add("case_records", {
            "id": f"case-{i:03d}",
            "document": f"Case document {i}",
            "metadata": {"silo_key": "ClientA_ProductA_Module1"},
        })

    graph = KnowledgeGraph()
    graph.build_from_vectordb(vdb, collections=["case_records"])

    # 3 chunk nodes + 1 shared silo node = 4
    assert graph.node_count == 4
    silo_node = graph.get_node("silo:ClientA_ProductA_Module1")
    assert silo_node is not None
    assert silo_node.type == "silo"


def test_build_from_vectordb_empty_collection_no_crash(tmp_path):
    from backend.knowledge.vectordb import VectorDB

    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_graph_empty"))
    graph = KnowledgeGraph()
    graph.build_from_vectordb(vdb, collections=["case_records"])

    assert graph.node_count == 0
    assert graph.edge_count == 0


def test_build_from_vectordb_thread_id_creates_thread_edge(tmp_path):
    from backend.knowledge.vectordb import VectorDB

    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_graph_thread"))
    vdb.add("weekly", {
        "id": "weekly-001",
        "document": "Weekly issue report",
        "metadata": {"issue_thread_id": "thread-xyz", "silo_key": ""},
    })

    graph = KnowledgeGraph()
    graph.build_from_vectordb(vdb, collections=["weekly"])

    assert "thread:thread-xyz" in graph.get_neighbors("weekly-001")
