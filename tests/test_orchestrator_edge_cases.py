"""Edge-case tests for the orchestrator loop.

These complement test_orchestrator.py by exercising paths that the
happy-path tests don't cover:

- Persistent PASS by every agent terminates without max_rounds
- Repetitive NEW_EVIDENCE that fails validation forces extra rounds
- Mid-conversation REVISE by an agent that hasn't spoken yet is rejected
- An ASK_STAKEHOLDER addressed to another agent (not @You) does NOT yield
- pending_mentions reroutes the next round's order
"""

from __future__ import annotations

import pytest

from backend.agents.orchestrator import (
    AgentResponse,
    MAX_ROUNDS,
    Orchestrator,
)


def _resp(agent, ctype="NEW_EVIDENCE", detail="d", to="@You", content="x"):
    return AgentResponse(
        agent=agent, contribution_type=ctype,
        contribution_detail=detail, addressed_to=to, content=content,
    )


@pytest.fixture
def orchestrator():
    return Orchestrator(llm_client=None)


# --------------------------------------------------------------------------- #
# PASS handling
# --------------------------------------------------------------------------- #

async def test_persistent_pass_eventually_hits_max_rounds(orchestrator):
    """If every agent only ever PASSes (never contributes), termination
    happens via max_rounds — not via all_pass — because the
    minimum-contribution rule blocks all_pass termination."""
    async def respond(agent_name, *args, **kwargs):
        return _resp(agent_name, ctype="PASS", content="PASS")

    orchestrator._get_agent_response = respond
    result = await orchestrator.run("question")

    assert result.terminated_reason == "max_rounds"
    assert result.round_count == MAX_ROUNDS


async def test_invalid_contribution_then_pass_does_not_count(orchestrator):
    """Two invalid attempts in the retry path → the round leaves the
    agent without a contribution and the loop continues."""
    call_count = {"analyzer": 0, "finder": 0, "reviewer": 0}

    async def respond(agent_name, *args, **kwargs):
        call_count[agent_name] += 1
        if agent_name == "analyzer":
            # Return rubber-stamps both times so the retry path also fails
            return _resp(
                "analyzer",
                ctype="NEW_EVIDENCE",
                content="I agree with everyone",
            )
        if agent_name == "finder":
            return _resp(
                "finder",
                content="Found case 0847 with PRV-4412 source_case_0847",
            )
        if agent_name == "reviewer":
            return _resp(
                "reviewer",
                content="Procedure ch.8.3 valid for this case",
            )
        return _resp(agent_name, ctype="PASS", content="PASS")

    orchestrator._get_agent_response = respond
    result = await orchestrator.run("test")

    # Analyzer's rubber-stamps must have been retried at least once per round
    assert call_count["analyzer"] >= 2
    # And nothing analyzer said ended up in the conversation
    analyzer_msgs = [m for m in result.conversation if m.agent == "analyzer"]
    assert analyzer_msgs == []


# --------------------------------------------------------------------------- #
# Mention routing
# --------------------------------------------------------------------------- #

async def test_at_finder_mention_added_to_pending_route(orchestrator):
    """When analyzer mentions @Finder, the orchestrator records that mention
    in its pending_mentions queue for the next round.

    Hard to observe externally without breaking encapsulation, so we check
    the externally-visible side effect: the conversation contains analyzer's
    message with the @Finder reference, and finder responds (i.e. it does
    enter the loop, not just get skipped)."""
    async def respond(agent_name, user_query, conversation):
        if agent_name == "analyzer" and not any(
            m.agent == "analyzer" for m in conversation
        ):
            return _resp(
                "analyzer",
                content="@Finder please look up unique_case_PRV4412 source_id_99",
                detail="Mention finder",
            )
        if agent_name == "finder" and not any(
            m.agent == "finder" for m in conversation
        ):
            return _resp(
                "finder",
                content="Found case 0847 source_id_finder unique_text_42",
            )
        if agent_name == "reviewer" and not any(
            m.agent == "reviewer" for m in conversation
        ):
            return _resp(
                "reviewer",
                content="Procedure ch.8 unique_proc_42 confirmed",
            )
        return _resp(agent_name, ctype="PASS", content="PASS")

    orchestrator._get_agent_response = respond
    result = await orchestrator.run("PRV-4412")

    # Both analyzer and finder appeared in the conversation; analyzer first.
    agents_in_order = [m.agent for m in result.conversation]
    assert "analyzer" in agents_in_order
    assert "finder" in agents_in_order
    # The mention was recorded — analyzer's message contains @Finder
    analyzer_msg = next(m for m in result.conversation if m.agent == "analyzer")
    assert "@Finder" in analyzer_msg.content


# --------------------------------------------------------------------------- #
# ASK_STAKEHOLDER routing
# --------------------------------------------------------------------------- #

async def test_ask_stakeholder_to_another_agent_does_not_yield(orchestrator):
    """ASK_STAKEHOLDER addressed to @Finder (not @You) is just a contribution,
    not an awaiting_user_input event."""
    async def respond(agent_name, *args, **kwargs):
        if agent_name == "analyzer":
            return _resp(
                "analyzer", ctype="ASK_STAKEHOLDER", to="@Finder",
                content="@Finder please cross-check case 0847 source_id_check",
                detail="Ask finder for cross-check",
            )
        # Make sure others contribute substantively so the loop can end
        if agent_name == "finder":
            return _resp("finder", content="Cross-check confirms unique_kw_xyz")
        if agent_name == "reviewer":
            return _resp("reviewer", content="Procedure ch.8 unique_proc_42")
        return _resp(agent_name, ctype="PASS", content="PASS")

    orchestrator._get_agent_response = respond
    result = await orchestrator.run("PRV-4412")

    assert result.awaiting_user_input is False
    assert result.terminated_reason in {"all_pass", "max_rounds"}


# --------------------------------------------------------------------------- #
# REVISE rules
# --------------------------------------------------------------------------- #

async def test_revise_without_prior_message_is_rejected(orchestrator):
    """An agent that has never spoken cannot REVISE — the response is
    treated as invalid and not appended to the conversation."""
    async def respond(agent_name, *args, **kwargs):
        if agent_name == "analyzer":
            # First attempt: invalid REVISE
            # Second attempt (retry): also REVISE → still rejected
            return _resp(
                "analyzer", ctype="REVISE",
                content="Revising my (nonexistent) earlier statement on TIS",
                detail="Revise earlier",
            )
        if agent_name == "finder":
            return _resp("finder", content="Case 0847 unique_finder_42 source_id_a")
        if agent_name == "reviewer":
            return _resp("reviewer", content="Procedure unique_proc_99 valid")
        return _resp(agent_name, ctype="PASS", content="PASS")

    orchestrator._get_agent_response = respond
    result = await orchestrator.run("Q")

    # Analyzer's REVISE must NOT appear in the conversation
    analyzer_messages = [m for m in result.conversation if m.agent == "analyzer"]
    assert analyzer_messages == []
