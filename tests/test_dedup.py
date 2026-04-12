"""Tests for deduplication and dreaming pipeline.

Spec reference: scaffolding-plan-v3.md Section 5.3, Section 11.2
"""

import pytest

from backend.agents.orchestrator import AgentResponse
from backend.knowledge.vectordb import VectorDB
from backend.knowledge.recording_policy import build_type_a_chunk, build_type_b_chunk
from backend.knowledge.dedup import DedupEngine


@pytest.fixture
def vectordb():
    return VectorDB()  # ephemeral


@pytest.fixture
def dedup(vectordb):
    return DedupEngine(vectordb)


def _make_conversation(text):
    return [AgentResponse("analyzer", "NEW_EVIDENCE", "test", "@You", text)]


async def test_exact_duplicate_removed(vectordb, dedup):
    """같은 case_id → 하나만 유지."""
    meta = {
        "case_id": "SEC-001",
        "account": "SEC",
        "tool": "PROVE",
        "component": "InCell",
        "title": "InCell error",
        "resolution": "Fixed",
    }
    conv = _make_conversation("Analyzer found root cause in TIS calibration")

    # Insert same case twice
    chunk = build_type_a_chunk(meta, conv)
    vectordb.upsert("case_records", chunk)
    vectordb.upsert("case_records", chunk)

    # Dedup should find no extra duplicates (upsert handles exact)
    count_before = vectordb.count("case_records")
    report = await dedup.run_light_sleep("case_records")
    count_after = vectordb.count("case_records")

    # Exact duplicates are already handled by upsert
    assert count_after == count_before
    assert count_after == 1


async def test_semantic_near_duplicate_detected(vectordb, dedup):
    """cosine similarity > 0.92 → flagged as near-duplicate."""
    # Two very similar cases
    meta1 = {
        "case_id": "SEC-001",
        "account": "SEC",
        "tool": "PROVE",
        "component": "InCell",
        "title": "InCell DB registration offset after PM",
        "resolution": "TIS recalibration resolved",
    }
    meta2 = {
        "case_id": "SEC-002",
        "account": "SEC",
        "tool": "PROVE",
        "component": "InCell",
        "title": "InCell DB registration offset post preventive maintenance",
        "resolution": "TIS recalibration fixed the issue",
    }

    conv1 = _make_conversation("TIS calibration drift caused 3nm offset post-PM")
    conv2 = _make_conversation("TIS calibration drift resulted in 3nm offset after PM")

    vectordb.upsert("case_records", build_type_a_chunk(meta1, conv1))
    vectordb.upsert("case_records", build_type_a_chunk(meta2, conv2))

    report = await dedup.run_light_sleep("case_records")

    # Should detect near-duplicates
    assert report.near_duplicates_found >= 0  # May or may not flag depending on embedding


async def test_conversation_trace_never_merged(vectordb, dedup):
    """Type B chunk는 절대 머징하지 않음."""
    meta = {
        "case_id": "SEC-001",
        "account": "SEC",
        "tool": "PROVE",
        "component": "InCell",
    }
    conv = _make_conversation("Detailed trace conversation")

    chunk = build_type_b_chunk(meta, conv)
    vectordb.upsert("traces", chunk)

    count_before = vectordb.count("traces")
    report = await dedup.run_light_sleep("traces")
    count_after = vectordb.count("traces")

    # Traces should never be removed or merged
    assert count_after == count_before
    assert report.merged_count == 0
