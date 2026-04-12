"""Integration tests — full case lifecycle through WebSocket + orchestrator.

Spec reference: scaffolding-plan-v3.md Section 11.3
"""

import json

import pytest

from backend.agents.orchestrator import AgentResponse, Orchestrator, OrchestratorResult
from backend.knowledge.vectordb import VectorDB
from backend.knowledge.database import ZemasDB
from backend.memory.case_recorder import CaseRecorder
from backend.memory.preloader import SessionPreloader


async def test_full_case_lifecycle():
    """
    Full scenario: user query → agent discussion → case close →
    Type A + Type B stored → next session pre-loads context.
    """
    vectordb = VectorDB()  # ephemeral
    db = ZemasDB(":memory:")
    recorder = CaseRecorder(vectordb, db)

    # Simulate orchestrator run with mock agent responses
    orchestrator = Orchestrator()

    round_num = 0
    responses = [
        # Round 1: each agent contributes
        AgentResponse("analyzer", "NEW_EVIDENCE", "Root cause: TIS timing issue post-PM",
                       "@You", "PRV-4412 error indicates timing sync failure between InCell and stage. "
                       "Based on error pattern, most likely root cause is TIS calibration drift."),
        AgentResponse("finder", "NEW_EVIDENCE", "Found similar case SEC-2025-0142",
                       "@Analyzer", "Case SEC-2025-0142 had same E4012 error. Resolved by firmware v3.2.1 update. "
                       "Also found TSMC-2025-0089 with related timing issue from cable degradation."),
        AgentResponse("reviewer", "NEW_EVIDENCE", "Procedure check per manual 8.4.2",
                       "@You", "PROVE Service Manual 8.4.2 requires: check SECS/GEM log, verify encoder, "
                       "run InCell self-test. Firmware update follows SOP-PROVE-042."),
        # Round 2: analyzer revises, others pass
        AgentResponse("analyzer", "REVISE", "Updated analysis with finder data",
                       "@You", "Revised: TIS firmware timing regression (matches SEC-2025-0142). "
                       "Recommend: 1) InCell self-test 2) Check firmware version 3) Update per SOP-PROVE-042"),
        AgentResponse("finder", "PASS", "", "", ""),
        AgentResponse("reviewer", "PASS", "", "", ""),
    ]

    async def mock_response(agent_name, query, conv):
        nonlocal round_num
        for r in responses:
            if r.agent == agent_name and r not in conv and r.contribution_type != "PASS":
                return r
        # Return PASS if no more responses
        return AgentResponse(agent_name, "PASS", "", "", "No further input.")

    orchestrator._get_agent_response = mock_response
    for name in ["analyzer", "finder", "reviewer"]:
        orchestrator.register_agent(name, None)

    result = await orchestrator.run("PRV-4412, 3nm offset, RS3.0, post-PM at SEC PROVE")

    assert result.terminated_reason in ("all_pass", "max_rounds")
    assert len(result.conversation) >= 3

    # Case close → record to ChromaDB + SQLite
    case_metadata = {
        "case_id": "SEC-2025-0200",
        "account": "SEC",
        "tool": "PROVE",
        "component": "InCell",
        "title": "PRV-4412 offset post-PM",
        "resolution": "TIS firmware update per SOP-PROVE-042",
    }
    type_a_id, type_b_id = await recorder.record_case(case_metadata, result.conversation)

    # Verify ChromaDB storage
    assert vectordb.get_by_id("case_records", type_a_id) is not None
    assert vectordb.get_by_id("traces", type_b_id) is not None

    # Verify SQLite storage
    case = db.get_case("SEC-2025-0200")
    assert case is not None
    assert case["status"] == "closed"
    assert case["account"] == "SEC"

    # Pre-load next session: this case should appear in context
    preloader = SessionPreloader(vectordb)
    context = await preloader.build_context(
        account="SEC", tool="PROVE", component="InCell",
        query="InCell offset error",
    )
    assert len(context.silo_cases) >= 1
    assert any("SEC-2025-0200" in c.get("metadata", {}).get("case_id", "")
               for c in context.silo_cases)


async def test_weekly_report_cross_reference():
    """
    Weekly report data is available for case resolution context.
    """
    vectordb = VectorDB()  # ephemeral

    # Bootstrap some weekly data
    from backend.knowledge.recording_policy import build_type_c_chunk

    weekly_rows = [
        {"cw": "CW14", "account": "SEC", "tool": "LE#3", "title": "SW 5.6.2 upgrade SECS/GEM 300 issue",
         "fob": "All", "status": "Ongoing", "next_plan": "Patch scheduled CW15"},
        {"cw": "CW15", "account": "SEC", "tool": "LE#3", "title": "SW 5.6.2 upgrade SECS/GEM 300 issue",
         "fob": "All", "status": "Resolved", "next_plan": "Verified"},
    ]

    for row in weekly_rows:
        chunk = build_type_c_chunk(row)
        vectordb.upsert("weekly", chunk)

    # Search for related weekly entries
    preloader = SessionPreloader(vectordb)
    context = await preloader.build_context(
        account="SEC", tool="PROVE", component="SECS/GEM",
        query="SECS/GEM 300 bug after SW upgrade",
    )

    assert len(context.weekly_entries) >= 1
    # Should find the SW upgrade issue
    found = any("SW" in e.get("document", "") or "SECS" in e.get("document", "")
                for e in context.weekly_entries)
    assert found
