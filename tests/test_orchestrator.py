"""TDD tests for the orchestrator collaborative loop.

Spec reference: scaffolding-plan-v3.md Section 3.1, Section 11.2, Section 12.3
Tests written BEFORE implementation.
"""

import pytest
from unittest.mock import AsyncMock, patch

from backend.agents.orchestrator import (
    AgentResponse,
    Orchestrator,
    MAX_ROUNDS,
)


def _make_response(
    agent: str,
    contribution_type: str = "NEW_EVIDENCE",
    contribution_detail: str = "Some new finding",
    addressed_to: str = "@You",
    content: str = "Test content with new information and source_id_123.",
    is_pass: bool = False,
) -> AgentResponse:
    return AgentResponse(
        agent=agent,
        contribution_type="PASS" if is_pass else contribution_type,
        contribution_detail="" if is_pass else contribution_detail,
        addressed_to=addressed_to,
        content="PASS" if is_pass else content,
    )


@pytest.fixture
def mock_llm():
    """Mock LLMClient that returns controlled responses."""
    llm = AsyncMock()
    return llm


@pytest.fixture
def orchestrator(mock_llm):
    """Orchestrator with mock LLM."""
    return Orchestrator(llm_client=mock_llm)


async def test_minimum_contribution_enforced(orchestrator, mock_llm):
    """모든 에이전트가 PASS 전에 최소 1회 기여해야 함."""
    call_count = {"analyzer": 0, "finder": 0, "reviewer": 0}

    async def mock_agent_respond(agent_name: str, *args, **kwargs):
        call_count[agent_name] += 1
        if call_count[agent_name] == 1:
            # First call: contribute
            return _make_response(
                agent=agent_name,
                content=f"New finding from {agent_name}: unique_info_{agent_name}",
                contribution_detail=f"Unique contribution from {agent_name}",
            )
        else:
            # Second call: pass
            return _make_response(agent=agent_name, is_pass=True)

    orchestrator._get_agent_response = mock_agent_respond

    result = await orchestrator.run("PRV-4412, 3nm offset, post-PM")

    # All agents should have been called at least once with real contribution
    for agent in ["analyzer", "finder", "reviewer"]:
        assert call_count[agent] >= 1, f"{agent} never contributed"

    assert result.terminated_reason != "error"


async def test_rubber_stamp_rejected(orchestrator, mock_llm):
    """'동의합니다'만 말하면 기여로 인정 안 됨."""
    call_count = {"analyzer": 0, "finder": 0, "reviewer": 0}

    async def mock_agent_respond(agent_name: str, *args, **kwargs):
        call_count[agent_name] += 1
        if agent_name == "analyzer":
            return _make_response(
                agent="analyzer",
                content="Root cause: TIS misalignment. Source: manual_ch8.",
                contribution_detail="TIS misalignment root cause",
            )
        if agent_name == "finder":
            if call_count["finder"] == 1:
                # First attempt: rubber stamp (should be rejected)
                return _make_response(
                    agent="finder",
                    contribution_type="NEW_EVIDENCE",
                    contribution_detail="Agreement with Analyzer",
                    content="I agree with @Analyzer that TIS is the issue.",
                )
            else:
                # Second attempt: real contribution
                return _make_response(
                    agent="finder",
                    content="Found Case #0847 with PRV-4412 pattern. source_id: case_0847",
                    contribution_detail="Found historical case #0847",
                )
        # reviewer
        if call_count["reviewer"] == 1:
            return _make_response(
                agent="reviewer",
                content="Ch.8.3 steps 4-7 are applicable. Procedure validated.",
                contribution_detail="Procedure validation for Ch.8.3",
            )
        return _make_response(agent=agent_name, is_pass=True)

    orchestrator._get_agent_response = mock_agent_respond

    result = await orchestrator.run("PRV-4412 offset issue")

    # Finder should have been called more than once (rubber stamp rejected)
    assert call_count["finder"] >= 2


async def test_agent_can_mention_other_agent(orchestrator, mock_llm):
    """@Analyzer, @Finder 등 mention이 올바르게 라우팅됨."""
    mentions_received = []

    async def mock_agent_respond(agent_name: str, *args, **kwargs):
        conversation = kwargs.get("conversation", args[1] if len(args) > 1 else [])
        # Check if this agent was mentioned in previous messages
        for msg in conversation:
            if f"@{agent_name.capitalize()}" in msg.content:
                mentions_received.append(agent_name)

        if agent_name == "analyzer":
            return _make_response(
                agent="analyzer",
                addressed_to="@Finder",
                content="@Finder can you search for cases with PRV-4412? New info: offset_3nm.",
                contribution_detail="Requesting Finder search for PRV-4412",
                contribution_type="ASK_STAKEHOLDER",
            )
        if agent_name == "finder":
            return _make_response(
                agent="finder",
                content="Found case #0847 matching PRV-4412. source_case_0847.",
                contribution_detail="Case #0847 search result",
            )
        return _make_response(agent=agent_name, is_pass=True)

    orchestrator._get_agent_response = mock_agent_respond

    result = await orchestrator.run("PRV-4412 offset")

    # Finder should have received the @Finder mention in its conversation context
    assert "finder" in mentions_received


async def test_ask_user_yields_turn(orchestrator, mock_llm):
    """ASK_STAKEHOLDER with @You시 user에게 턴이 넘어감."""
    async def mock_agent_respond(agent_name: str, *args, **kwargs):
        if agent_name == "reviewer":
            return _make_response(
                agent="reviewer",
                contribution_type="ASK_STAKEHOLDER",
                addressed_to="@You",
                content="@You did the SE confirm TIS was skipped during PM?",
                contribution_detail="Requesting SE confirmation about TIS skip",
            )
        return _make_response(
            agent=agent_name,
            content=f"Analysis from {agent_name}: unique_data_{agent_name}",
            contribution_detail=f"Contribution from {agent_name}",
        )

    orchestrator._get_agent_response = mock_agent_respond

    result = await orchestrator.run("PRV-4412 offset")

    assert result.awaiting_user_input is True
    assert "@You" in result.last_message.addressed_to


async def test_max_rounds_terminates(orchestrator, mock_llm):
    """15라운드 초과 시 강제 종료 + 요약 생성."""
    call_count = 0

    async def mock_agent_respond(agent_name: str, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Always contribute, never PASS — forces max rounds
        return _make_response(
            agent=agent_name,
            content=f"Round {call_count} finding: new_data_{call_count}",
            contribution_detail=f"Round {call_count} unique finding",
        )

    orchestrator._get_agent_response = mock_agent_respond

    result = await orchestrator.run("Complex issue that never resolves")

    assert result.terminated_reason == "max_rounds"
    assert result.round_count <= MAX_ROUNDS


async def test_all_pass_terminates(orchestrator, mock_llm):
    """모든 에이전트가 기여 후 PASS하면 종료."""
    call_count = {"analyzer": 0, "finder": 0, "reviewer": 0}

    async def mock_agent_respond(agent_name: str, *args, **kwargs):
        call_count[agent_name] += 1
        if call_count[agent_name] == 1:
            return _make_response(
                agent=agent_name,
                content=f"Contribution from {agent_name}: unique_info_{agent_name}",
                contribution_detail=f"Initial analysis from {agent_name}",
            )
        return _make_response(agent=agent_name, is_pass=True)

    orchestrator._get_agent_response = mock_agent_respond

    result = await orchestrator.run("Simple issue")

    assert result.terminated_reason == "all_pass"
    assert result.round_count <= 3  # Should complete in ~2 rounds
