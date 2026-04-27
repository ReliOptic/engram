"""Regression tests for bottleneck fixes (2026-04-27).

Covers:
- orchestrator round-1 parallel execution
- orchestrator retry with rejection context injection
- VectorDB async_search / async_search_by_silo non-blocking wrappers
- DedupEngine numpy cosine similarity (no extra embedding API calls)
"""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from backend.agents.orchestrator import AgentResponse, Orchestrator, AGENT_ORDER
from backend.knowledge.vectordb import VectorDB
from backend.knowledge.dedup import DedupEngine


def _make_response(
    agent: str,
    contribution_type: str = "NEW_EVIDENCE",
    contribution_detail: str = "Some unique finding",
    addressed_to: str = "@You",
    content: str = "Unique content with source_id and evidence_xyz.",
    is_pass: bool = False,
) -> AgentResponse:
    return AgentResponse(
        agent=agent,
        contribution_type="PASS" if is_pass else contribution_type,
        contribution_detail="" if is_pass else contribution_detail,
        addressed_to=addressed_to,
        content="PASS" if is_pass else content,
    )


# ---------------------------------------------------------------------------
# Test 1: Round-1 parallel execution
# ---------------------------------------------------------------------------

async def test_round_1_all_agents_called_via_parallel_prefetch():
    """Round 1 with standard order calls all 3 agents via asyncio.gather prefetch path.

    Verifies that the parallel prefetch fires all 3 agents before the per-agent
    validation loop begins, rather than calling them one-by-one sequentially.
    """
    gather_snapshots: list[list[str]] = []
    call_log: list[str] = []

    orchestrator = Orchestrator()

    async def mock_get_agent_response(
        agent_name: str, user_query: str, conversation: list[AgentResponse]
    ) -> AgentResponse:
        call_log.append(agent_name)
        return _make_response(
            agent=agent_name,
            content=f"Round-1 finding from {agent_name}: unique_token_{agent_name}",
            contribution_detail=f"Unique analysis from {agent_name}",
        )

    original_gather = asyncio.gather

    async def spy_gather(*coros, **kwargs):
        # Record the snapshot of call_log at the moment gather is invoked.
        # If gather is used for the round-1 prefetch, call_log is still empty
        # because no individual calls have been made yet.
        gather_snapshots.append(list(call_log))
        return await original_gather(*coros, **kwargs)

    orchestrator._get_agent_response = mock_get_agent_response

    with patch("backend.agents.orchestrator.asyncio.gather", side_effect=spy_gather):
        result = await orchestrator.run("PRV-4412 offset after PM")

    # gather must have been called at least once (the round-1 prefetch)
    assert len(gather_snapshots) >= 1, "asyncio.gather was never called"

    # At the moment gather fired in round 1, no individual sequential calls
    # had been made yet — the snapshot should be empty
    assert gather_snapshots[0] == [], (
        "Round-1 gather fired after some agents were already called sequentially; "
        "parallel prefetch is not working"
    )

    # All three agents must eventually be in call_log
    for agent in AGENT_ORDER:
        assert agent in call_log, f"Agent '{agent}' was never called"


# ---------------------------------------------------------------------------
# Test 2: Retry with rejection context injection
# ---------------------------------------------------------------------------

async def test_retry_injects_rejection_context_into_conversation():
    """On rubber-stamp, retry passes a system rejection AgentResponse in conversation.

    The rejection AgentResponse must have agent='system' and content containing
    the word 'rejected' so the LLM knows why its previous response was dropped.
    """
    retry_conversations: list[list[AgentResponse]] = []
    call_count: dict[str, int] = {"analyzer": 0, "finder": 0, "reviewer": 0}

    orchestrator = Orchestrator()

    async def mock_get_agent_response(
        agent_name: str, user_query: str, conversation: list[AgentResponse]
    ) -> AgentResponse:
        call_count[agent_name] += 1

        if agent_name == "finder":
            if call_count["finder"] == 1:
                # First attempt: rubber-stamp — will be rejected
                return _make_response(
                    agent="finder",
                    contribution_type="NEW_EVIDENCE",
                    contribution_detail="Agreement",
                    content="I agree with Analyzer that TIS is the root cause.",
                )
            else:
                # Capture the conversation the retry receives
                retry_conversations.append(list(conversation))
                return _make_response(
                    agent="finder",
                    content="Found case #0847 with PRV-4412 pattern. source_id: case_0847",
                    contribution_detail="Historical case #0847 found",
                )

        if agent_name == "analyzer":
            return _make_response(
                agent="analyzer",
                content="Root cause: TIS drift. Source: manual_ch8_ref.",
                contribution_detail="TIS drift root cause identified",
            )

        # reviewer
        if call_count["reviewer"] == 1:
            return _make_response(
                agent="reviewer",
                content="Procedure ch.8.3 steps 4-7 validated. source_proc_ref.",
                contribution_detail="Procedure validation complete",
            )
        return _make_response(agent=agent_name, is_pass=True)

    orchestrator._get_agent_response = mock_get_agent_response

    await orchestrator.run("PRV-4412 offset issue")

    # Finder must have been called at least twice (initial + retry)
    assert call_count["finder"] >= 2, "Finder was not retried after rubber-stamp"

    # The retry conversation must exist
    assert len(retry_conversations) >= 1, "No retry conversation was captured"

    retry_conv = retry_conversations[0]

    # There must be a system-role message in the retry conversation
    system_messages = [msg for msg in retry_conv if msg.agent == "system"]
    assert len(system_messages) >= 1, (
        "No system rejection message found in retry conversation"
    )

    rejection_msg = system_messages[-1]
    assert "rejected" in rejection_msg.content.lower(), (
        f"Rejection message does not contain 'rejected': {rejection_msg.content!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: VectorDB async_search / async_search_by_silo return lists
# ---------------------------------------------------------------------------

async def test_async_search_returns_list_of_results(tmp_path):
    """async_search delegates to sync search() and returns a list.

    The autouse fake_embedding_function fixture ensures no real OpenRouter calls.
    """
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_async_search"))

    vdb.add("case_records", {
        "id": "doc-001",
        "document": "TIS calibration offset after preventive maintenance",
        "metadata": {"account": "ClientA", "tool": "ProductA", "silo_key": "ClientA_ProductA_Module1"},
    })
    vdb.add("case_records", {
        "id": "doc-002",
        "document": "Valve pressure drop in cooling circuit",
        "metadata": {"account": "ClientA", "tool": "ProductA", "silo_key": "ClientA_ProductA_Module2"},
    })

    results = await vdb.async_search("case_records", "TIS offset", n_results=3)

    assert isinstance(results, list)


async def test_async_search_by_silo_returns_list_of_results(tmp_path):
    """async_search_by_silo delegates to sync search_by_silo() and returns a list.

    The autouse fake_embedding_function fixture ensures no real OpenRouter calls.
    """
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_async_search_by_silo"))

    vdb.add("case_records", {
        "id": "silo-001",
        "document": "Module1 DB registration error after PM",
        "metadata": {
            "account": "ClientA",
            "tool": "ProductA",
            "component": "Module1",
            "silo_key": "ClientA_ProductA_Module1",
        },
    })
    vdb.add("case_records", {
        "id": "silo-002",
        "document": "Module2 coolant flow issue",
        "metadata": {
            "account": "ClientA",
            "tool": "ProductA",
            "component": "Module2",
            "silo_key": "ClientA_ProductA_Module2",
        },
    })

    results = await vdb.async_search_by_silo(
        "case_records", "offset", "ClientA", "ProductA", n_results=3
    )

    assert isinstance(results, list)


async def test_async_search_on_empty_collection_returns_empty_list(tmp_path):
    """async_search returns [] when the collection is empty (same as sync search)."""
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_empty"))

    results = await vdb.async_search("case_records", "anything", n_results=5)

    assert results == []


# ---------------------------------------------------------------------------
# Test 4: DedupEngine uses stored embeddings — no extra col.query calls
# ---------------------------------------------------------------------------

async def test_dedup_light_sleep_uses_stored_embeddings_not_query(tmp_path):
    """run_light_sleep computes cosine similarity from stored embeddings, not col.query.

    Verifies that the numpy dot-product path is taken and col.query is not
    invoked during the near-duplicate scan (which would trigger extra embedding
    API calls on every document).
    """
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_dedup1"))

    for i in range(3):
        vdb.add("case_records", {
            "id": f"case-{i:03d}",
            "document": f"Unique case document number {i}: different_token_{i}",
            "metadata": {"account": "ClientA", "tool": "ProductA"},
        })

    assert vdb.count("case_records") == 3

    dedup = DedupEngine(vdb)

    # Spy on col.query to verify it is NOT called during run_light_sleep
    col = vdb._get_collection("case_records")
    original_query = col.query
    query_call_count = {"n": 0}

    def spy_query(*args, **kwargs):
        query_call_count["n"] += 1
        return original_query(*args, **kwargs)

    col.query = spy_query

    report = await dedup.run_light_sleep("case_records")

    # Restore original
    col.query = original_query

    # col.query must NOT have been called — embeddings come from col.get, not col.query
    assert query_call_count["n"] == 0, (
        f"col.query was called {query_call_count['n']} time(s) during run_light_sleep; "
        "dedup must use stored embeddings via col.get, not re-query"
    )

    assert report.total_items == 3
    assert isinstance(report.merge_candidates, list)


async def test_dedup_light_sleep_reports_correct_item_count(tmp_path):
    """run_light_sleep total_items matches the number of documents in the collection."""
    vdb = VectorDB(persist_dir=str(tmp_path / "chroma_dedup2"))

    for i in range(5):
        vdb.add("case_records", {
            "id": f"item-{i}",
            "document": f"Case record {i} with distinct content variant_{i}",
            "metadata": {"account": "ClientB", "tool": "ProductB"},
        })

    dedup = DedupEngine(vdb)
    report = await dedup.run_light_sleep("case_records")

    assert report.total_items == 5
    assert report.collection == "case_records"
    assert isinstance(report.merge_candidates, list)
