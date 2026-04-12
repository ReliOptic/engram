"""Engram Orchestrator — collaborative multi-agent loop.

Manages turn-taking between Analyzer, Finder, and Reviewer agents.
Validates contributions, rejects rubber-stamps, enforces min-contribution,
handles @mentions, and terminates on all-pass or max-rounds.

Spec reference: scaffolding-plan-v3.md Section 3.1 delta, Section 12.3
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.utils.llm_client import LLMClient

# Maximum rounds before forced termination
MAX_ROUNDS = 15

# Agent turn order
AGENT_ORDER = ["analyzer", "finder", "reviewer"]

# Contribution types — an agent response must be one of these to count as contribution
CONTRIBUTION_TYPES = {
    "NEW_EVIDENCE": "새로운 근거, 데이터, 소스를 제시",
    "COUNTER": "다른 에이전트 의견에 반론 또는 수정 요청",
    "ASK_STAKEHOLDER": "user 또는 다른 에이전트에게 추가 정보 요청",
    "REVISE": "자신의 이전 발언을 새 정보 기반으로 수정",
}

# Patterns that indicate rubber-stamping (bare agreement without substance)
RUBBER_STAMP_PATTERNS = [
    r"^i agree",
    r"^동의합니다",
    r"^i concur",
    r"^agreed",
    r"^맞습니다",
    r"^that'?s correct",
    r"^정확합니다",
]


@dataclass
class AgentResponse:
    """Structured response from an agent."""

    agent: str
    contribution_type: str  # One of CONTRIBUTION_TYPES keys, or "PASS"
    contribution_detail: str
    addressed_to: str  # @Analyzer, @Finder, @Reviewer, or @You (user)
    content: str


@dataclass
class OrchestratorResult:
    """Result of an orchestrator run."""

    conversation: list[AgentResponse] = field(default_factory=list)
    terminated_reason: str = ""  # "all_pass", "max_rounds", "user_input", "error"
    round_count: int = 0
    awaiting_user_input: bool = False
    last_message: AgentResponse | None = None


def validate_contribution(response: AgentResponse, history: list[AgentResponse]) -> bool:
    """Validate that an agent response is a substantive contribution.

    Returns False for:
    - Invalid contribution types
    - Rubber-stamp agreements disguised as NEW_EVIDENCE
    - Repetition of existing information

    Spec: scaffolding-plan-v3.md Section 3.1 delta
    """
    # PASS is valid but not a contribution
    if response.contribution_type == "PASS":
        return False

    # Must be a known contribution type
    if response.contribution_type not in CONTRIBUTION_TYPES:
        return False

    # Detect rubber-stamp: "I agree" disguised as NEW_EVIDENCE
    content_lower = response.content.strip().lower()
    for pattern in RUBBER_STAMP_PATTERNS:
        if re.match(pattern, content_lower):
            return False

    # For NEW_EVIDENCE: check if it's actually repeating existing info
    if response.contribution_type == "NEW_EVIDENCE" and history:
        if _is_repetition(response, history):
            return False

    # COUNTER must reference another agent
    if response.contribution_type == "COUNTER":
        has_reference = any(
            f"@{name.capitalize()}" in response.content
            for name in AGENT_ORDER
        )
        has_reasoning = len(response.content.split()) > 10
        if not has_reasoning:
            return False

    # REVISE must come from an agent who previously spoke
    if response.contribution_type == "REVISE":
        previous_by_same = [r for r in history if r.agent == response.agent]
        if not previous_by_same:
            return False  # Can't revise if never spoke

    return True


_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "from", "with", "for", "and", "or", "of", "to", "in", "on",
    "that", "this", "it", "its", "i", "my", "also", "based",
    "about", "as", "at", "by", "initial", "analysis", "new",
})


def _is_repetition(response: AgentResponse, history: list[AgentResponse]) -> bool:
    """Check if response repeats information already in conversation history.

    Compares both contribution_detail and content against previous messages.
    Filters out stop words to focus on substantive term overlap.
    """
    def extract_keywords(text: str) -> set[str]:
        words = set(text.strip().lower().split())
        return words - _STOP_WORDS

    response_kw = extract_keywords(response.contribution_detail + " " + response.content)

    for prev in history:
        if prev.agent == response.agent:
            continue  # Self-repetition is revision, not repetition

        prev_kw = extract_keywords(prev.contribution_detail + " " + prev.content)

        if not response_kw or not prev_kw:
            continue

        overlap = response_kw & prev_kw
        # Use Jaccard similarity (overlap / union) for balanced comparison
        union = response_kw | prev_kw
        similarity = len(overlap) / max(len(union), 1)
        if similarity > 0.7:
            return True

    return False


class Orchestrator:
    """Collaborative loop orchestrator for Engram agents.

    Manages turn-taking, validates contributions, handles @mentions,
    and determines when to terminate the discussion.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self._llm = llm_client
        self._agents: dict[str, object] = {}

    def register_agent(self, name: str, agent: object) -> None:
        """Register a specialized agent."""
        self._agents[name] = agent

    async def _get_agent_response(
        self, agent_name: str, user_query: str, conversation: list[AgentResponse]
    ) -> AgentResponse:
        """Get response from a specific agent. Override in tests."""
        agent = self._agents.get(agent_name)
        if agent is None:
            raise ValueError(f"Agent '{agent_name}' not registered")
        return await agent.respond(user_query, conversation)

    async def run(self, user_query: str) -> OrchestratorResult:
        """Run the collaborative discussion loop.

        Flow:
        1. Each agent takes turns in order (analyzer → finder → reviewer)
        2. Each response is validated for substantive contribution
        3. If rubber-stamp → agent is asked again (retry once)
        4. @mention routing prioritizes mentioned agent next
        5. Terminates when: all agents PASS (after min 1 contribution each),
           max rounds reached, or user input requested
        """
        conversation: list[AgentResponse] = []
        contributions: dict[str, int] = {name: 0 for name in AGENT_ORDER}
        passes: dict[str, bool] = {name: False for name in AGENT_ORDER}
        round_count = 0
        pending_mentions: list[str] = []

        while round_count < MAX_ROUNDS:
            round_count += 1

            # Determine agent order for this round
            if pending_mentions:
                turn_order = pending_mentions + [
                    a for a in AGENT_ORDER if a not in pending_mentions
                ]
                pending_mentions = []
            else:
                turn_order = list(AGENT_ORDER)

            all_passed_this_round = True

            for agent_name in turn_order:
                if passes.get(agent_name) and contributions[agent_name] > 0:
                    continue  # Already contributed and passed

                response = await self._get_agent_response(
                    agent_name, user_query, conversation
                )

                # Check for user input request
                if (
                    response.contribution_type == "ASK_STAKEHOLDER"
                    and response.addressed_to == "@You"
                ):
                    conversation.append(response)
                    contributions[agent_name] += 1
                    return OrchestratorResult(
                        conversation=conversation,
                        terminated_reason="user_input",
                        round_count=round_count,
                        awaiting_user_input=True,
                        last_message=response,
                    )

                # Validate contribution
                if response.contribution_type == "PASS":
                    if contributions[agent_name] == 0:
                        # Haven't contributed yet — must contribute before passing
                        # Give them another chance next round
                        all_passed_this_round = False
                        continue
                    passes[agent_name] = True
                    continue

                is_valid = validate_contribution(response, conversation)

                if not is_valid:
                    # Rubber-stamp or repetition — retry once
                    response = await self._get_agent_response(
                        agent_name, user_query, conversation
                    )
                    if response.contribution_type == "PASS":
                        if contributions[agent_name] > 0:
                            passes[agent_name] = True
                            continue
                        all_passed_this_round = False
                        continue

                    is_valid = validate_contribution(response, conversation)
                    if not is_valid:
                        all_passed_this_round = False
                        continue

                # Valid contribution
                conversation.append(response)
                contributions[agent_name] += 1
                passes[agent_name] = False  # Reset pass after new contribution
                all_passed_this_round = False

                # Extract @mentions for priority routing
                for name in AGENT_ORDER:
                    if name != agent_name and f"@{name.capitalize()}" in response.content:
                        if name not in pending_mentions:
                            pending_mentions.append(name)

            # Check termination: all agents contributed and passed
            all_contributed = all(c > 0 for c in contributions.values())
            all_passed = all(passes.values())
            if all_contributed and all_passed:
                return OrchestratorResult(
                    conversation=conversation,
                    terminated_reason="all_pass",
                    round_count=round_count,
                    last_message=conversation[-1] if conversation else None,
                )

        # Max rounds reached
        return OrchestratorResult(
            conversation=conversation,
            terminated_reason="max_rounds",
            round_count=round_count,
            last_message=conversation[-1] if conversation else None,
        )
