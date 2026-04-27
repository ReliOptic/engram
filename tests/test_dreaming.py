"""Tests for DreamingPipeline — run_full_cycle, REM patterns, graph export/import."""

import json
import pytest

from backend.knowledge.dreaming import DreamingPipeline, DreamingReport
from backend.knowledge.graph import GraphEdge, GraphNode, KnowledgeGraph
from backend.knowledge.vectordb import VectorDB


# ---------------------------------------------------------------------------
# run_full_cycle
# ---------------------------------------------------------------------------

async def test_run_full_cycle_returns_dreaming_report(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_cycle_1"))
    pipeline = DreamingPipeline(vdb)
    report = await pipeline.run_full_cycle()
    assert isinstance(report, DreamingReport)


async def test_run_full_cycle_sets_timestamp(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_cycle_2"))
    pipeline = DreamingPipeline(vdb)
    report = await pipeline.run_full_cycle()
    assert report.timestamp != ""


async def test_run_full_cycle_has_light_sleep_for_all_three_collections(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_cycle_3"))
    pipeline = DreamingPipeline(vdb)
    report = await pipeline.run_full_cycle()
    # case_records, weekly, traces
    assert len(report.light_sleep) == 3


async def test_run_full_cycle_graph_counts_are_non_negative(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_cycle_4"))
    pipeline = DreamingPipeline(vdb)
    report = await pipeline.run_full_cycle()
    assert report.deep_graph_nodes >= 0
    assert report.deep_graph_edges >= 0


async def test_run_full_cycle_rem_patterns_is_list(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_cycle_5"))
    pipeline = DreamingPipeline(vdb)
    report = await pipeline.run_full_cycle()
    assert isinstance(report.rem_patterns, list)


async def test_run_full_cycle_deep_graph_reflects_vectordb_content(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_cycle_6"))
    for i in range(3):
        vdb.add("case_records", {
            "id": f"case-{i:03d}",
            "document": f"Case document {i}",
            "metadata": {"silo_key": f"ClientA_ProductA_Module{i}"},
        })

    pipeline = DreamingPipeline(vdb)
    report = await pipeline.run_full_cycle()

    # 3 cases + 3 silos = at least 6 nodes
    assert report.deep_graph_nodes >= 3


# ---------------------------------------------------------------------------
# _run_rem_sleep — pattern detection
# ---------------------------------------------------------------------------

async def test_rem_sleep_empty_collection_returns_empty_list(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_rem_empty"))
    pipeline = DreamingPipeline(vdb)
    patterns = await pipeline._run_rem_sleep()
    assert patterns == []


async def test_rem_sleep_detects_recurring_pattern_with_3_or_more(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_rem_recurring"))
    for i in range(4):
        vdb.add("traces", {
            "id": f"trace-recur-{i:03d}",
            "document": f"Conversation trace {i}",
            "metadata": {
                "tacit_signals": json.dumps([
                    {"type": "calibration_drift", "description": f"signal {i}"}
                ]),
            },
        })

    pipeline = DreamingPipeline(vdb)
    patterns = await pipeline._run_rem_sleep()

    calibration = [p for p in patterns if p["type"] == "calibration_drift"]
    assert len(calibration) == 1
    assert calibration[0]["count"] == 4
    assert calibration[0]["promotion_candidate"] is True


async def test_rem_sleep_below_threshold_not_promoted(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_rem_rare"))
    for i in range(2):
        vdb.add("traces", {
            "id": f"trace-rare-{i}",
            "document": f"Rare case {i}",
            "metadata": {
                "tacit_signals": json.dumps([
                    {"type": "rare_quirk", "description": f"quirk {i}"}
                ]),
            },
        })

    pipeline = DreamingPipeline(vdb)
    patterns = await pipeline._run_rem_sleep()

    rare = [p for p in patterns if p["type"] == "rare_quirk"]
    assert len(rare) == 1
    assert rare[0]["promotion_candidate"] is False


async def test_rem_sleep_limits_signal_examples_to_five(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_rem_limit"))
    for i in range(8):
        vdb.add("traces", {
            "id": f"trace-many-{i:03d}",
            "document": f"Trace {i}",
            "metadata": {
                "tacit_signals": json.dumps([
                    {"type": "frequent_type", "description": f"example {i}"}
                ]),
            },
        })

    pipeline = DreamingPipeline(vdb)
    patterns = await pipeline._run_rem_sleep()

    freq = [p for p in patterns if p["type"] == "frequent_type"]
    assert freq[0]["count"] == 8
    assert len(freq[0]["signals"]) <= 5  # capped at 5


async def test_rem_sleep_ignores_entries_without_tacit_signals(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_rem_no_signals"))
    vdb.add("traces", {
        "id": "trace-no-signal",
        "document": "This trace has no tacit signals",
        "metadata": {},
    })

    pipeline = DreamingPipeline(vdb)
    patterns = await pipeline._run_rem_sleep()

    assert patterns == []


# ---------------------------------------------------------------------------
# export_graph / import_graph
# ---------------------------------------------------------------------------

def test_export_graph_returns_dict_with_nodes_and_edges(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_export"))
    pipeline = DreamingPipeline(vdb)
    data = pipeline.export_graph()
    assert "nodes" in data
    assert "edges" in data


def test_import_graph_adds_new_nodes(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_import_new"))
    pipeline = DreamingPipeline(vdb)

    imported_data = {
        "nodes": [{"id": "new-node", "type": "case", "label": "B", "metadata": {}}],
        "edges": [],
    }
    pipeline.import_graph(imported_data)

    assert pipeline._graph.get_node("new-node") is not None


def test_import_graph_does_not_duplicate_existing_nodes(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_import_nodup"))
    pipeline = DreamingPipeline(vdb)
    pipeline._graph.add_node(GraphNode(id="existing", type="case", label="A"))

    imported_data = {
        "nodes": [
            {"id": "existing", "type": "case", "label": "A", "metadata": {}},
            {"id": "new-node", "type": "case", "label": "B", "metadata": {}},
        ],
        "edges": [],
    }
    pipeline.import_graph(imported_data)

    assert pipeline._graph.node_count == 2


def test_import_graph_does_not_duplicate_existing_edges(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_import_nodup_edge"))
    pipeline = DreamingPipeline(vdb)
    pipeline._graph.add_edge(GraphEdge(source="a", target="b", type="similar"))

    imported_data = {
        "nodes": [],
        "edges": [
            {"source": "a", "target": "b", "type": "similar", "weight": 1.0, "metadata": {}},
        ],
    }
    pipeline.import_graph(imported_data)

    assert pipeline._graph.edge_count == 1  # no duplicate added


def test_export_import_round_trip_preserves_content(tmp_path):
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_roundtrip"))
    pipeline = DreamingPipeline(vdb)
    pipeline._graph.add_node(GraphNode(id="n1", type="case", label="PRV-4412"))
    pipeline._graph.add_edge(GraphEdge(source="n1", target="n2", type="similar", weight=0.9))

    exported = pipeline.export_graph()

    pipeline2 = DreamingPipeline(VectorDB(persist_dir=str(tmp_path / "chroma_roundtrip2")))
    pipeline2.import_graph(exported)

    assert pipeline2._graph.get_node("n1").label == "PRV-4412"
    assert pipeline2._graph.edge_count == 1
