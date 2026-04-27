"""Tests for the CaseRecorder dual-write to ChromaDB + SQLite + sync queue.

Covers:
- Type A and Type B chunks land in the right collections
- Returned IDs match the deterministic ID format (case-* / trace-*)
- SQLite case is created+closed when an EngramDB is provided
- Existing cases are not re-created (idempotent close)
- Sync queue receives a 'case_closed' event with both chunks in the payload
- Recorder works without optional db / sync_queue (degraded modes)
- Empty conversations don't break recording
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.agents.orchestrator import AgentResponse
from backend.knowledge.database import EngramDB
from backend.knowledge.vectordb import VectorDB
from backend.memory.case_recorder import CaseRecorder
from backend.sync.queue import SyncQueue


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def vectordb(tmp_path):
    return VectorDB(persist_dir=str(tmp_path / "chroma_recorder"))


@pytest.fixture
def db(tmp_path):
    return EngramDB(str(tmp_path / "engram.db"))


@pytest.fixture
def sync_queue(db):
    return SyncQueue(db._conn)


def _conv() -> list[AgentResponse]:
    return [
        AgentResponse(
            agent="analyzer",
            contribution_type="NEW_EVIDENCE",
            contribution_detail="Root cause: TIS calibration drift",
            addressed_to="@You",
            content="Symptom suggests calibration drift after PM",
        ),
        AgentResponse(
            agent="finder",
            contribution_type="NEW_EVIDENCE",
            contribution_detail="Found prior case #0847",
            addressed_to="@Analyzer",
            content="Case 0847 had identical TIS drift symptoms",
        ),
        AgentResponse(
            agent="reviewer",
            contribution_type="NEW_EVIDENCE",
            contribution_detail="Procedure validated",
            addressed_to="@You",
            content="Manual ch.8.3 steps 4-7 apply",
        ),
    ]


def _meta(case_id="ClientA-001"):
    return {
        "case_id": case_id,
        "account": "ClientA",
        "tool": "ProductA",
        "component": "Module1",
        "title": "Module1 offset post-PM",
        "resolution": "TIS recalibration",
    }


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

async def test_record_case_writes_both_chunks(vectordb):
    """Type A → case_records; Type B → traces. IDs follow case-/trace- prefix."""
    recorder = CaseRecorder(vectordb)
    type_a_id, type_b_id = await recorder.record_case(_meta(), _conv())

    assert type_a_id == "case-ClientA-001"
    assert type_b_id == "trace-ClientA-001"
    assert vectordb.count("case_records") == 1
    assert vectordb.count("traces") == 1


async def test_record_case_metadata_silo_key_format(vectordb):
    """Stored chunk metadata uses silo_key = account_tool_component."""
    recorder = CaseRecorder(vectordb)
    await recorder.record_case(_meta(), _conv())

    stored = vectordb.get_by_id("case_records", "case-ClientA-001")
    assert stored is not None
    assert stored["metadata"]["silo_key"] == "ClientA_ProductA_Module1"
    assert stored["metadata"]["chunk_type"] == "case_record"
    # message_count == len(conversation)
    assert stored["metadata"]["message_count"] == 3


async def test_record_case_persists_to_sqlite(vectordb, db):
    """When a db is supplied, the case is created (if new) and closed."""
    recorder = CaseRecorder(vectordb, db=db)
    await recorder.record_case(_meta(), _conv())

    case = db.get_case("ClientA-001")
    assert case is not None
    assert case["status"] == "closed"
    assert case["resolution"] == "TIS recalibration"
    assert case["closed_at"] is not None


async def test_record_case_does_not_recreate_existing_case(vectordb, db):
    """If the case already exists in SQLite, it is closed in place — not duplicated."""
    db.create_case(
        case_id="ClientA-001",
        account="ClientA", tool="ProductA",
        component="Module1", title="Pre-existing",
    )
    recorder = CaseRecorder(vectordb, db=db)
    await recorder.record_case(_meta(), _conv())

    cases = db.list_cases(account="ClientA")
    # exactly one row for that case_id
    assert sum(1 for c in cases if c["case_id"] == "ClientA-001") == 1
    case = db.get_case("ClientA-001")
    assert case["status"] == "closed"


async def test_record_case_pushes_sync_event(vectordb, db, sync_queue):
    """A case_closed event lands in the sync queue with both chunks in payload."""
    recorder = CaseRecorder(vectordb, db=db, sync_queue=sync_queue)
    await recorder.record_case(_meta(), _conv())

    pending = sync_queue.get_pending()
    assert len(pending) == 1
    event = pending[0]
    assert event["event_type"] == "case_closed"
    assert event["collection"] == "case_records"
    assert event["entity_id"] == "ClientA-001"

    payload = event["payload"]
    assert payload["case_id"] == "ClientA-001"
    assert payload["resolution"] == "TIS recalibration"
    assert "type_a_chunk" in payload
    assert "type_b_chunk" in payload
    assert payload["type_a_chunk"]["id"] == "case-ClientA-001"
    assert payload["type_b_chunk"]["id"] == "trace-ClientA-001"


async def test_record_case_without_db_or_sync(vectordb):
    """Recorder works without optional db / sync_queue (vector-only mode)."""
    recorder = CaseRecorder(vectordb, db=None, sync_queue=None)
    type_a_id, type_b_id = await recorder.record_case(_meta(), _conv())

    # No exceptions; vector store updated
    assert vectordb.count("case_records") == 1
    assert vectordb.count("traces") == 1
    assert type_a_id and type_b_id


async def test_record_case_with_empty_conversation(vectordb, db):
    """An empty conversation still produces valid chunks (no agents required)."""
    recorder = CaseRecorder(vectordb, db=db)
    type_a_id, _ = await recorder.record_case(_meta("ClientA-empty"), [])

    assert vectordb.count("case_records") == 1
    stored = vectordb.get_by_id("case_records", type_a_id)
    assert stored["metadata"]["message_count"] == 0
    assert stored["metadata"]["agent_count"] == 0


async def test_record_case_upsert_is_idempotent(vectordb):
    """Recording the same case twice keeps a single chunk (deterministic ID)."""
    recorder = CaseRecorder(vectordb)
    await recorder.record_case(_meta(), _conv())
    await recorder.record_case(_meta(), _conv())

    assert vectordb.count("case_records") == 1
    assert vectordb.count("traces") == 1
