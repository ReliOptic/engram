"""TDD tests for VectorDB recording policy.

Spec reference: scaffolding-plan-v3.md Section 5.1, Section 11.2
Tests written BEFORE implementation.
"""

import pytest

from backend.agents.orchestrator import AgentResponse
from backend.knowledge.vectordb import VectorDB
from backend.knowledge.recording_policy import (
    build_type_a_chunk,
    build_type_b_chunk,
    build_type_c_chunk,
)
from backend.memory.case_recorder import CaseRecorder


@pytest.fixture
def vectordb(tmp_path):
    """Create a VectorDB instance with temp persist directory."""
    return VectorDB(persist_dir=str(tmp_path / "chroma_test"))


@pytest.fixture
def sample_conversation():
    """Sample agent conversation for case recording."""
    return [
        AgentResponse(
            agent="analyzer",
            contribution_type="NEW_EVIDENCE",
            contribution_detail="Root cause analysis: TIS misalignment",
            addressed_to="@You",
            content="Root cause: TIS misalignment at 78% probability. "
                    "Error PRV-4412 indicates offset after PM. Source: manual_ch8.",
        ),
        AgentResponse(
            agent="finder",
            contribution_type="COUNTER",
            contribution_detail="Historical case contradicts TIS-only hypothesis",
            addressed_to="@Analyzer",
            content="Case #0847 showed ref mark degradation caused similar offset. "
                    "Source: case_record_0847. TIS probability should be lower.",
        ),
        AgentResponse(
            agent="analyzer",
            contribution_type="REVISE",
            contribution_detail="Revised probabilities based on case data",
            addressed_to="@You",
            content="Revised: TIS 65%, ref mark 25%. Finder's case data shifts the distribution.",
        ),
        AgentResponse(
            agent="reviewer",
            contribution_type="NEW_EVIDENCE",
            contribution_detail="Procedure validation for Ch.8.3",
            addressed_to="@You",
            content="Ch.8.3 steps 4-7 are applicable. Procedure APPROVED. "
                    "Recommend TIS recalibration first, then ref mark check.",
        ),
    ]


@pytest.fixture
def case_metadata():
    """Sample case metadata."""
    return {
        "case_id": "CASE-2026-0042",
        "account": "ClientA",
        "tool": "ProductA",
        "component": "Module1",
        "title": "PRV-4412 3nm offset post-PM",
        "resolution": "TIS recalibration + ref mark verification",
    }


async def test_case_close_creates_type_a(vectordb, sample_conversation, case_metadata):
    """케이스 종료 시 Type A (case_record) chunk 생성."""
    recorder = CaseRecorder(vectordb)
    await recorder.record_case(case_metadata, sample_conversation)

    results = vectordb.search("case_records", "PRV-4412 offset", n_results=5)
    assert len(results) >= 1
    # Type A chunk should exist
    chunk_types = [r["metadata"]["chunk_type"] for r in results]
    assert "case_record" in chunk_types


async def test_case_close_creates_type_b(vectordb, sample_conversation, case_metadata):
    """케이스 종료 시 Type B (conversation_trace) chunk 생성."""
    recorder = CaseRecorder(vectordb)
    await recorder.record_case(case_metadata, sample_conversation)

    results = vectordb.search("traces", "TIS misalignment", n_results=5)
    assert len(results) >= 1
    chunk_types = [r["metadata"]["chunk_type"] for r in results]
    assert "conversation_trace" in chunk_types


async def test_type_a_has_required_fields(vectordb, sample_conversation, case_metadata):
    """Type A chunk에 모든 필수 필드 존재."""
    chunk = build_type_a_chunk(case_metadata, sample_conversation)

    required_fields = ["case_id", "account", "tool", "component", "silo_key",
                       "chunk_type", "title", "resolution"]
    for field in required_fields:
        assert field in chunk["metadata"], f"Missing field: {field}"

    assert chunk["metadata"]["chunk_type"] == "case_record"


async def test_silo_key_format(vectordb, sample_conversation, case_metadata):
    """silo key가 {account}_{tool}_{component} 형식."""
    chunk = build_type_a_chunk(case_metadata, sample_conversation)
    silo_key = chunk["metadata"]["silo_key"]
    assert silo_key == "ClientA_ProductA_Module1"


async def test_weekly_creates_type_c():
    """xlsx 행 데이터 → Type C (weekly_report) chunk 생성."""
    row_data = {
        "cw": "CW15",
        "account": "ClientA",
        "fob": "LE#3",
        "tool": "ProductA",
        "title": "Protocol 300 bug after SW 5.6.2 upgrade",
        "status": "Open",
        "next_plan": "Rollback to 5.6.1 if patch unavailable",
    }

    chunk = build_type_c_chunk(row_data)

    assert chunk["metadata"]["chunk_type"] == "weekly_report"
    assert chunk["metadata"]["cw"] == "CW15"
    assert chunk["metadata"]["silo_key"] == "ClientA_ProductA_Protocol"
    assert "Protocol 300 bug" in chunk["document"]


async def test_weekly_issue_threading(vectordb):
    """같은 이슈가 여러 주에 걸치면 issue_thread_id 연결."""
    # Same issue across CW14 and CW15
    row_cw14 = {
        "cw": "CW14",
        "account": "ClientA",
        "fob": "LE#3",
        "tool": "ProductA",
        "title": "Protocol 300 bug after SW upgrade",
        "status": "Open",
        "next_plan": "Investigating",
    }
    row_cw15 = {
        "cw": "CW15",
        "account": "ClientA",
        "fob": "LE#3",
        "tool": "ProductA",
        "title": "Protocol 300 bug after SW 5.6.2 upgrade",
        "status": "Open",
        "next_plan": "Rollback to 5.6.1",
    }

    chunk_14 = build_type_c_chunk(row_cw14)
    chunk_15 = build_type_c_chunk(row_cw15)

    vectordb.add("weekly", chunk_14)
    vectordb.add("weekly", chunk_15)

    # Both should share an issue_thread_id based on account+tool+similar title
    results = vectordb.search(
        "weekly", "Protocol bug", n_results=5,
        where={"account": "ClientA"},
    )
    assert len(results) >= 2

    thread_ids = {r["metadata"].get("issue_thread_id") for r in results}
    # At least they should both have a thread_id
    assert all(r["metadata"].get("issue_thread_id") for r in results)
    # And they should share the same thread_id
    assert len(thread_ids) == 1
