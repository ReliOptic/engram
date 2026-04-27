"""Tests for the nightly dreaming pipeline.

Covers:
- Light Sleep: dedup runs over case_records / weekly / traces
  (with traces protected from merging)
- REM Sleep: tacit-signal pattern detection (3+ occurrences = promotion candidate)
- Deep Sleep: graph build → node/edge counts populated on the report
- Full cycle: timestamp + all stages produce non-empty reports
- Graph export → import roundtrip via DreamingPipeline
"""

from __future__ import annotations

import json

import pytest

from backend.agents.orchestrator import AgentResponse
from backend.knowledge.dreaming import DreamingPipeline, DreamingReport
from backend.knowledge.graph import GraphEdge, GraphNode, KnowledgeGraph
from backend.knowledge.recording_policy import (
    build_type_a_chunk,
    build_type_b_chunk,
    build_type_c_chunk,
)
from backend.knowledge.vectordb import VectorDB


@pytest.fixture
def vectordb(tmp_path):
    """Per-test VectorDB. ChromaDB's in-memory Client is a process-level
    singleton, so we use a fresh persist dir to keep tests isolated."""
    return VectorDB(persist_dir=str(tmp_path / "chroma_dreaming"))


@pytest.fixture
def pipeline(vectordb):
    return DreamingPipeline(vectordb)


def _conv(text: str) -> list[AgentResponse]:
    return [AgentResponse("analyzer", "NEW_EVIDENCE", "d", "@You", text)]


def _seed_case(vectordb, case_id: str, title: str, account="ClientA",
               tool="ProductA", component="Module1"):
    meta = {
        "case_id": case_id, "account": account, "tool": tool,
        "component": component, "title": title, "resolution": f"Fixed {case_id}",
    }
    vectordb.upsert("case_records", build_type_a_chunk(meta, _conv(title)))
    return meta


def _seed_trace_with_signals(vectordb, case_id: str, signals: list[dict]):
    """Create a Type-B trace and stamp tacit_signals into its metadata."""
    meta = {
        "case_id": case_id, "account": "ClientA",
        "tool": "ProductA", "component": "Module1",
    }
    chunk = build_type_b_chunk(meta, _conv(f"trace for {case_id}"))
    chunk["metadata"]["tacit_signals"] = json.dumps(signals)
    vectordb.upsert("traces", chunk)


# --------------------------------------------------------------------------- #
# Full cycle + structural
# --------------------------------------------------------------------------- #

async def test_full_cycle_returns_report_with_timestamp(pipeline):
    """A full cycle on an empty DB still returns a structured report."""
    report = await pipeline.run_full_cycle()
    assert isinstance(report, DreamingReport)
    assert report.timestamp  # ISO-format string
    # Light Sleep visited each of the three collections
    assert {r.collection for r in report.light_sleep} == {
        "case_records", "weekly", "traces",
    }
    # REM patterns and graph default to empty
    assert report.rem_patterns == []
    assert report.deep_graph_nodes == 0
    assert report.deep_graph_edges == 0


async def test_full_cycle_traces_skipped_in_light_sleep(pipeline, vectordb):
    """Traces collection is counted but never merged in Light Sleep."""
    _seed_trace_with_signals(vectordb, "C1", [
        {"type": "field_decision", "text": "skip TIS"},
    ])

    report = await pipeline.run_full_cycle()
    traces_report = next(r for r in report.light_sleep if r.collection == "traces")

    assert traces_report.skipped_traces == 1
    assert traces_report.merged_count == 0
    assert vectordb.count("traces") == 1  # nothing removed


# --------------------------------------------------------------------------- #
# REM Sleep — tacit signal pattern detection
# --------------------------------------------------------------------------- #

async def test_rem_sleep_promotes_signals_with_three_or_more(pipeline, vectordb):
    """A signal type that appears 3+ times is a promotion candidate."""
    for i in range(4):
        _seed_trace_with_signals(vectordb, f"C{i}", [
            {"type": "field_decision", "text": f"obs-{i}"},
        ])

    report = await pipeline.run_full_cycle()

    field_pattern = next(
        (p for p in report.rem_patterns if p["type"] == "field_decision"),
        None,
    )
    assert field_pattern is not None
    assert field_pattern["count"] == 4
    assert field_pattern["promotion_candidate"] is True
    # Top-N examples capped at 5
    assert len(field_pattern["signals"]) <= 5


async def test_rem_sleep_below_threshold_not_promoted(pipeline, vectordb):
    """A signal type with <3 occurrences is reported but not promoted."""
    _seed_trace_with_signals(vectordb, "C1", [
        {"type": "tool_quirk", "text": "bug"},
    ])
    _seed_trace_with_signals(vectordb, "C2", [
        {"type": "tool_quirk", "text": "bug2"},
    ])

    report = await pipeline.run_full_cycle()
    quirk = next(p for p in report.rem_patterns if p["type"] == "tool_quirk")
    assert quirk["count"] == 2
    assert quirk["promotion_candidate"] is False


async def test_rem_sleep_handles_malformed_signal_metadata(pipeline, vectordb):
    """Invalid JSON in tacit_signals is silently ignored, not fatal."""
    meta = {
        "case_id": "Cbad", "account": "ClientA",
        "tool": "ProductA", "component": "Module1",
    }
    chunk = build_type_b_chunk(meta, _conv("trace"))
    chunk["metadata"]["tacit_signals"] = "not-json{"
    vectordb.upsert("traces", chunk)

    report = await pipeline.run_full_cycle()
    # No patterns extracted from the bad row; pipeline still completes.
    assert report.rem_patterns == []


# --------------------------------------------------------------------------- #
# Deep Sleep — graph build
# --------------------------------------------------------------------------- #

async def test_deep_sleep_populates_graph_counts(pipeline, vectordb):
    """A few cases should yield case nodes + a silo node + belongs_to edges."""
    _seed_case(vectordb, "ClientA-001", "Bug A")
    _seed_case(vectordb, "ClientA-002", "Bug B")

    report = await pipeline.run_full_cycle()
    # 2 case nodes + 1 silo node = 3
    assert report.deep_graph_nodes >= 3
    # 2 belongs_to edges (one per case)
    assert report.deep_graph_edges >= 2


async def test_deep_sleep_includes_weekly_thread_links(pipeline, vectordb):
    """Weekly chunks contribute thread nodes + thread edges."""
    chunk = build_type_c_chunk({
        "cw": "CW15-2026", "account": "ClientA", "tool": "ProductA",
        "title": "Module1 SECS/GEM bug after SW upgrade",
        "fob": "FOB1", "status": "open", "next_plan": "investigate",
    })
    vectordb.upsert("weekly", chunk)

    report = await pipeline.run_full_cycle()
    # weekly chunk + silo node + thread node = 3
    assert report.deep_graph_nodes >= 3
    # belongs_to (silo) + thread = 2
    assert report.deep_graph_edges >= 2


# --------------------------------------------------------------------------- #
# Graph export / import roundtrip
# --------------------------------------------------------------------------- #

async def test_export_and_import_graph_roundtrip(pipeline, vectordb):
    """Exported graph can be re-imported into a fresh pipeline without loss."""
    _seed_case(vectordb, "ClientA-001", "Bug A")
    await pipeline.run_full_cycle()

    exported = pipeline.export_graph()
    assert exported["nodes"] and exported["edges"]

    # Fresh pipeline (empty graph), then import
    fresh = DreamingPipeline(VectorDB())
    fresh._graph = KnowledgeGraph()  # ensure empty regardless of singleton state
    fresh.import_graph(exported)

    assert fresh._graph.node_count == len(exported["nodes"])
    assert fresh._graph.edge_count == len(exported["edges"])


async def test_import_graph_skips_existing_nodes_and_edges(pipeline):
    """Importing a graph that overlaps with an existing one merges, not duplicates."""
    # Seed pipeline graph manually
    pipeline._graph.add_node(GraphNode("n1", "case", "Case 1"))
    pipeline._graph.add_node(GraphNode("n2", "case", "Case 2"))
    pipeline._graph.add_edge(GraphEdge("n1", "n2", "similar", weight=0.9))

    incoming = {
        "nodes": [
            {"id": "n1", "type": "case", "label": "Case 1", "metadata": {}},
            {"id": "n3", "type": "case", "label": "Case 3", "metadata": {}},
        ],
        "edges": [
            # duplicate of existing edge — should be skipped
            {"source": "n1", "target": "n2", "type": "similar",
             "weight": 0.9, "metadata": {}},
            # new edge
            {"source": "n1", "target": "n3", "type": "similar",
             "weight": 0.7, "metadata": {}},
        ],
    }
    pipeline.import_graph(incoming)

    # n1, n2 from before + n3 added = 3
    assert pipeline._graph.node_count == 3
    # Existing similar edge preserved (1) + 1 new edge = 2
    assert pipeline._graph.edge_count == 2
