"""Tests for BaseAgent: prompt loading, message building, response parsing.

Covers:
- load_agent_config parses YAML frontmatter (scalars + lists) and body
- load_common_prompt reads common.md (cached)
- BaseAgent loads role config and exposes display_name / expertise
- _build_messages produces system + context + history + user query
- _parse_response handles JSON, fenced JSON code blocks, and free-form text
- AnalyzerAgent / FinderAgent / ReviewerAgent each load their own config
"""

from __future__ import annotations

import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.analyzer import AnalyzerAgent
from backend.agents.base_agent import (
    BaseAgent,
    _parse_yaml_simple,
    load_agent_config,
    load_common_prompt,
)
from backend.agents.finder import FinderAgent
from backend.agents.orchestrator import AgentResponse
from backend.agents.reviewer import ReviewerAgent
from backend.utils.llm_client import LLMResponse


# --------------------------------------------------------------------------- #
# YAML frontmatter parser
# --------------------------------------------------------------------------- #

def test_parse_yaml_simple_scalars_and_lists():
    text = textwrap.dedent("""\
        role: analyzer
        display_name: Analyzer
        expertise:
          - Symptom analysis
          - Error code interpretation
    """)
    result = _parse_yaml_simple(text)
    assert result["role"] == "analyzer"
    assert result["display_name"] == "Analyzer"
    assert result["expertise"] == [
        "Symptom analysis", "Error code interpretation",
    ]


def test_parse_yaml_simple_strips_quotes():
    text = 'description: "Knowledge search specialist"\nrole: \'finder\''
    result = _parse_yaml_simple(text)
    assert result["description"] == "Knowledge search specialist"
    assert result["role"] == "finder"


def test_parse_yaml_simple_empty_returns_empty_dict():
    assert _parse_yaml_simple("") == {}


# --------------------------------------------------------------------------- #
# load_agent_config / load_common_prompt
# --------------------------------------------------------------------------- #

def test_load_agent_config_returns_metadata_and_body():
    cfg = load_agent_config("analyzer")
    assert cfg["role"] == "analyzer"
    assert cfg["display_name"] == "Analyzer"
    assert isinstance(cfg["expertise"], list) and cfg["expertise"]
    assert "ROOT CAUSE ANALYSIS" in cfg["system_prompt"]


def test_load_common_prompt_is_cached_and_nonempty():
    a = load_common_prompt()
    b = load_common_prompt()
    assert a == b  # cached returns same instance
    assert a  # non-empty


# --------------------------------------------------------------------------- #
# BaseAgent — message building / parsing
# --------------------------------------------------------------------------- #

@pytest.fixture
def llm():
    return AsyncMock()


def _llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content, model="m", provider="openrouter",
        prompt_tokens=1, completion_tokens=1, total_tokens=2,
        estimated_cost_usd=0.0,
    )


def test_base_agent_loads_role_metadata(llm):
    agent = AnalyzerAgent(llm)
    assert agent.role == "analyzer"
    assert agent.display_name == "Analyzer"
    assert "Symptom analysis" in agent.expertise
    assert agent.system_prompt.startswith("You are the Analyzer")


def test_build_messages_includes_system_context_and_query(llm):
    agent = AnalyzerAgent(llm)
    history = [
        AgentResponse(
            agent="finder", contribution_type="NEW_EVIDENCE",
            contribution_detail="d", addressed_to="@Analyzer",
            content="Found case 0847",
        ),
    ]
    messages = agent._build_messages(
        user_query="PRV-4412", conversation=history, context="prior cases…"
    )

    # 1 system (prompt+common) + 1 system (context) + 1 history + 1 user
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert "ROOT CAUSE ANALYSIS" in messages[0]["content"]
    assert messages[1]["role"] == "system"
    assert "Context:" in messages[1]["content"]
    # History message: from another agent → role=user, with [FINDER] tag
    assert messages[2]["role"] == "user"
    assert "[FINDER]" in messages[2]["content"]
    # Final user query is tagged [USER QUERY]
    assert messages[3]["role"] == "user"
    assert "[USER QUERY] PRV-4412" in messages[3]["content"]


def test_build_messages_self_tagged_as_assistant(llm):
    """A history message authored by *this* agent is tagged role=assistant."""
    agent = AnalyzerAgent(llm)
    history = [
        AgentResponse(
            agent="analyzer", contribution_type="NEW_EVIDENCE",
            contribution_detail="d", addressed_to="@You", content="my prior take",
        ),
    ]
    msgs = agent._build_messages("q", history)
    self_msg = msgs[1]
    assert self_msg["role"] == "assistant"
    assert "[ANALYZER]" in self_msg["content"]


def test_parse_response_pure_json(llm):
    agent = AnalyzerAgent(llm)
    parsed = agent._parse_response(_llm_response(
        '{"contribution_type": "NEW_EVIDENCE", '
        '"contribution_detail": "TIS drift root cause", '
        '"addressed_to": "@Finder", '
        '"content": "Calibration drift after PM"}'
    ))
    assert parsed.agent == "analyzer"
    assert parsed.contribution_type == "NEW_EVIDENCE"
    assert parsed.contribution_detail == "TIS drift root cause"
    assert parsed.addressed_to == "@Finder"
    assert parsed.content == "Calibration drift after PM"


def test_parse_response_fenced_json(llm):
    agent = AnalyzerAgent(llm)
    fenced = (
        "Here is my analysis:\n"
        "```json\n"
        '{"contribution_type": "COUNTER", '
        '"contribution_detail": "Disagree with Finder", '
        '"addressed_to": "@Finder", '
        '"content": "Different root cause likely"}\n'
        "```"
    )
    parsed = agent._parse_response(_llm_response(fenced))
    assert parsed.contribution_type == "COUNTER"
    assert parsed.addressed_to == "@Finder"


def test_parse_response_freeform_falls_back_to_new_evidence(llm):
    """Non-JSON content becomes NEW_EVIDENCE addressed to user."""
    agent = AnalyzerAgent(llm)
    parsed = agent._parse_response(_llm_response("Just a plain text answer."))
    assert parsed.agent == "analyzer"
    assert parsed.contribution_type == "NEW_EVIDENCE"
    assert parsed.contribution_detail == "Unstructured response"
    assert parsed.addressed_to == "@You"
    assert parsed.content == "Just a plain text answer."


async def test_respond_calls_llm_with_role(llm):
    """BaseAgent.respond dispatches to llm.complete with its own role name."""
    agent = AnalyzerAgent(llm)
    llm.complete = AsyncMock(return_value=_llm_response(
        '{"contribution_type": "PASS", "contribution_detail": "", '
        '"addressed_to": "@You", "content": "PASS"}'
    ))

    parsed = await agent.respond("query", [])
    llm.complete.assert_awaited_once()
    role_arg = llm.complete.await_args.args[0]
    assert role_arg == "analyzer"
    assert parsed.contribution_type == "PASS"


# --------------------------------------------------------------------------- #
# Per-agent specialization
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("cls,role,prompt_keyword", [
    (AnalyzerAgent, "analyzer", "ROOT CAUSE ANALYSIS"),
    (FinderAgent,   "finder",   "KNOWLEDGE SEARCH"),
    (ReviewerAgent, "reviewer", "PROCEDURE VALIDATION"),
])
def test_each_specialist_loads_its_own_config(llm, cls, role, prompt_keyword):
    agent = cls(llm)
    assert agent.role == role
    assert prompt_keyword in agent.system_prompt
    # Each agent has at least one expertise bullet from its md
    assert len(agent.expertise) >= 1
