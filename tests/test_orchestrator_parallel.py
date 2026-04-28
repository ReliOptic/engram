"""Tests for orchestrator parallelization and timeout."""

from __future__ import annotations

import asyncio
import time

import pytest

from backend.agents.orchestrator import AGENT_ORDER, AgentResponse, Orchestrator


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


def _make_slow_agent(name: str, delay: float = 0.05):
    """Return an async callable that sleeps `delay` seconds then returns a valid response."""

    async def respond(agent_name: str, user_query: str, conversation: list[AgentResponse]) -> AgentResponse:
        await asyncio.sleep(delay)
        return _make_response(
            agent=agent_name,
            content=f"Contribution from {agent_name}: unique_data_{agent_name}_{len(conversation)}",
            contribution_detail=f"Unique finding from {agent_name}",
        )

    return respond


@pytest.fixture
def orchestrator():
    return Orchestrator()


async def test_all_rounds_run_agents_in_parallel(orchestrator):
    """Round 2+ with standard turn_order should run agents in parallel.

    3 agents each delay 0.05s. Sequential would take ≥0.15s per round.
    Parallel should complete each round in ~0.05s.
    """
    call_count = {"analyzer": 0, "finder": 0, "reviewer": 0}
    round2_call_times: dict[str, float] = {}

    async def mock_respond(agent_name: str, user_query: str, conversation: list[AgentResponse]) -> AgentResponse:
        is_round2 = len(conversation) == 3  # After round 1 all 3 contributed
        if is_round2:
            round2_call_times[agent_name] = asyncio.get_running_loop().time()

        await asyncio.sleep(0.05)
        call_count[agent_name] += 1

        if call_count[agent_name] == 1:
            return _make_response(
                agent=agent_name,
                content=f"Initial finding from {agent_name}: unique_token_{agent_name}",
                contribution_detail=f"Unique finding {agent_name}",
            )
        # Round 2+: PASS after first contribution
        return _make_response(agent=agent_name, is_pass=True)

    orchestrator._get_agent_response = mock_respond

    t0 = time.monotonic()
    result = await orchestrator.run("test query", timeout_secs=5.0)
    elapsed = time.monotonic() - t0

    # All 3 agents delay 0.05s each round.
    # Round 1 parallel: ~0.05s. Round 2 parallel: ~0.05s.
    # Total should be well under 0.15s * 2 rounds = 0.30s sequential time.
    # With parallel both rounds: ≈0.10s + overhead. Allow up to 0.35s.
    assert elapsed < 0.35, (
        f"Expected parallel execution (~0.10s), but took {elapsed:.3f}s — "
        "suggests sequential execution"
    )
    assert result.terminated_reason == "all_pass"
    assert set(round2_call_times) == set(AGENT_ORDER)
    round2_spread = max(round2_call_times.values()) - min(round2_call_times.values())
    assert round2_spread < 0.05, (
        f"Round 2 agents should start nearly simultaneously "
        f"(spread={round2_spread:.3f}s)"
    )


async def test_timeout_terminates_early(orchestrator):
    """Agents that take 5s each should be cut off by timeout_secs=0.1."""

    async def slow_respond(agent_name: str, user_query: str, conversation: list[AgentResponse]) -> AgentResponse:
        await asyncio.sleep(5.0)
        return _make_response(agent=agent_name)

    orchestrator._get_agent_response = slow_respond

    t0 = time.monotonic()
    result = await orchestrator.run("test query", timeout_secs=0.1)
    elapsed = time.monotonic() - t0

    assert result.terminated_reason == "timeout", (
        f"Expected 'timeout', got '{result.terminated_reason}'"
    )
    assert elapsed < 0.5, f"Should have stopped within 0.5s, took {elapsed:.3f}s"


async def test_timeout_preserves_partial_conversation(orchestrator):
    """Fast agents contribute before timeout; slow ones are cut by the deadline.

    Round 1 runs all 3 agents in parallel at 0.01s each — well within 0.3s timeout.
    Round 2 agents sleep 5s, so the deadline is hit before they produce output.
    The conversation from round 1 must be preserved.
    """
    call_count = {"analyzer": 0, "finder": 0, "reviewer": 0}

    async def mixed_respond(agent_name: str, user_query: str, conversation: list[AgentResponse]) -> AgentResponse:
        call_count[agent_name] += 1
        if call_count[agent_name] == 1:
            # Round 1: fast response
            await asyncio.sleep(0.01)
            return _make_response(
                agent=agent_name,
                content=f"Fast contribution from {agent_name}: data_{agent_name}",
                contribution_detail=f"Fast unique finding {agent_name}",
            )
        # Round 2+: very slow
        await asyncio.sleep(5.0)
        return _make_response(agent=agent_name, is_pass=True)

    orchestrator._get_agent_response = mixed_respond

    result = await orchestrator.run("test query", timeout_secs=0.3)

    assert result.terminated_reason == "timeout", (
        f"Expected 'timeout', got '{result.terminated_reason}'"
    )
    # Round 1 should have completed (3 fast responses)
    assert len(result.conversation) > 0, "Partial conversation should be preserved"


async def test_existing_round1_parallel_behavior_preserved(orchestrator):
    """Round 1 was already parallel — ensure it still is after the refactor."""
    first_call_times: dict[str, float] = {}
    first_call_conversation_lengths: dict[str, int] = {}

    async def timed_respond(agent_name: str, user_query: str, conversation: list[AgentResponse]) -> AgentResponse:
        if agent_name not in first_call_times:
            first_call_times[agent_name] = asyncio.get_running_loop().time()
            first_call_conversation_lengths[agent_name] = len(conversation)
        await asyncio.sleep(0.05)

        if not conversation:  # Round 1
            return _make_response(
                agent=agent_name,
                content=f"Round 1 finding: unique_{agent_name}_token",
                contribution_detail=f"Round 1 unique data from {agent_name}",
            )
        return _make_response(agent=agent_name, is_pass=True)

    orchestrator._get_agent_response = timed_respond

    t0 = time.monotonic()
    await orchestrator.run("test query", timeout_secs=5.0)
    elapsed = time.monotonic() - t0

    # All three agents should have been called; their start times should be
    # within ~0.02s of each other (parallel dispatch).
    assert len(first_call_times) == 3, "All 3 agents must be called in round 1"
    assert first_call_conversation_lengths == {
        agent: 0 for agent in AGENT_ORDER
    }, "Round 1 prefetch should give every agent the same empty snapshot"
    times = list(first_call_times.values())
    spread = max(times) - min(times)
    assert spread < 0.05, (
        f"Round 1 agents should start nearly simultaneously (spread={spread:.3f}s), "
        "got wide spread suggesting sequential dispatch"
    )
    # Overall round 1 should complete in ~0.05s not ~0.15s
    assert elapsed < 0.30, f"Parallel round 1 should be fast, took {elapsed:.3f}s"


async def test_timeout_result_has_round_count(orchestrator):
    """OrchestratorResult on timeout should include the current round_count."""

    async def slow_respond(agent_name: str, user_query: str, conversation: list[AgentResponse]) -> AgentResponse:
        await asyncio.sleep(5.0)
        return _make_response(agent=agent_name)

    orchestrator._get_agent_response = slow_respond

    result = await orchestrator.run("test query", timeout_secs=0.05)

    assert result.terminated_reason == "timeout"
    assert result.round_count >= 1
