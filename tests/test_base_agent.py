"""Tests for BaseAgent — YAML parser, response parsing, message building."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agents.base_agent import _parse_yaml_simple
from backend.utils.llm_client import LLMClient, LLMResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _llm_resp(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        provider="test",
        prompt_tokens=10,
        completion_tokens=10,
        total_tokens=20,
        estimated_cost_usd=0.0,
    )


@pytest.fixture
def analyzer(models_config):
    """Real AnalyzerAgent with a mock LLM client."""
    from backend.agents.analyzer import AnalyzerAgent
    llm = MagicMock(spec=LLMClient)
    return AnalyzerAgent(llm)


@pytest.fixture
def finder(models_config):
    """Real FinderAgent with a mock LLM client."""
    from backend.agents.finder import FinderAgent
    llm = MagicMock(spec=LLMClient)
    return FinderAgent(llm)


# ---------------------------------------------------------------------------
# _parse_yaml_simple
# ---------------------------------------------------------------------------

def test_parse_yaml_simple_key_value_pairs():
    yaml = "role: analyzer\ndisplay_name: Analyzer"
    result = _parse_yaml_simple(yaml)
    assert result["role"] == "analyzer"
    assert result["display_name"] == "Analyzer"


def test_parse_yaml_simple_list_values():
    yaml = "expertise:\n- vibration analysis\n- thermal diagnosis\n- pressure drops"
    result = _parse_yaml_simple(yaml)
    assert result["expertise"] == ["vibration analysis", "thermal diagnosis", "pressure drops"]


def test_parse_yaml_simple_mixed_key_and_list():
    yaml = "role: finder\nreference_manuals:\n- Manual A\n- Manual B\ndescription: Finds past cases"
    result = _parse_yaml_simple(yaml)
    assert result["role"] == "finder"
    assert result["reference_manuals"] == ["Manual A", "Manual B"]
    assert result["description"] == "Finds past cases"


def test_parse_yaml_simple_empty_string_returns_empty_dict():
    assert _parse_yaml_simple("") == {}


def test_parse_yaml_simple_ignores_blank_lines():
    yaml = "role: reviewer\n\ndescription: Validates procedures"
    result = _parse_yaml_simple(yaml)
    assert result["role"] == "reviewer"
    assert result["description"] == "Validates procedures"


def test_parse_yaml_simple_strips_quotes():
    yaml = 'role: "analyzer"\ndescription: \'Root cause specialist\''
    result = _parse_yaml_simple(yaml)
    assert result["role"] == "analyzer"
    assert result["description"] == "Root cause specialist"


# ---------------------------------------------------------------------------
# BaseAgent._parse_response
# ---------------------------------------------------------------------------

def test_parse_response_valid_json(analyzer):
    payload = (
        '{"contribution_type":"NEW_EVIDENCE",'
        '"contribution_detail":"TIS calibration drift",'
        '"addressed_to":"@finder",'
        '"content":"Root cause is TIS drift."}'
    )
    result = analyzer._parse_response(_llm_resp(payload))

    assert result.agent == "analyzer"
    assert result.contribution_type == "NEW_EVIDENCE"
    assert result.contribution_detail == "TIS calibration drift"
    assert result.addressed_to == "@finder"
    assert result.content == "Root cause is TIS drift."


def test_parse_response_json_in_markdown_code_block(analyzer):
    payload = (
        "```json\n"
        '{"contribution_type":"COUNTER","contribution_detail":"Disagrees","addressed_to":"@analyzer","content":"Not TIS."}\n'
        "```"
    )
    result = analyzer._parse_response(_llm_resp(payload))

    assert result.contribution_type == "COUNTER"
    assert result.content == "Not TIS."


def test_parse_response_invalid_json_falls_back_to_new_evidence(analyzer):
    raw_content = "This is an unstructured free-form response from the LLM."
    result = analyzer._parse_response(_llm_resp(raw_content))

    assert result.agent == "analyzer"
    assert result.contribution_type == "NEW_EVIDENCE"
    assert result.content == raw_content


def test_parse_response_pass_type_preserved(analyzer):
    payload = '{"contribution_type":"PASS","contribution_detail":"","addressed_to":"@You","content":"PASS"}'
    result = analyzer._parse_response(_llm_resp(payload))

    assert result.contribution_type == "PASS"


def test_parse_response_uses_correct_agent_role(finder):
    payload = '{"contribution_type":"NEW_EVIDENCE","contribution_detail":"Found case","addressed_to":"@analyzer","content":"Case #0847 found."}'
    result = finder._parse_response(_llm_resp(payload))

    assert result.agent == "finder"


# ---------------------------------------------------------------------------
# BaseAgent._build_messages
# ---------------------------------------------------------------------------

def test_build_messages_starts_with_system_role(analyzer):
    messages = analyzer._build_messages("PRV-4412 issue", conversation=[])
    assert messages[0]["role"] == "system"


def test_build_messages_ends_with_user_query(analyzer):
    messages = analyzer._build_messages("PRV-4412 issue", conversation=[])
    last = messages[-1]
    assert last["role"] == "user"
    assert "PRV-4412 issue" in last["content"]


def test_build_messages_own_responses_mapped_to_assistant(analyzer):
    from backend.agents.orchestrator import AgentResponse
    own_resp = AgentResponse(
        agent="analyzer",
        contribution_type="NEW_EVIDENCE",
        contribution_detail="found root cause",
        addressed_to="@You",
        content="Root cause is X.",
    )
    messages = analyzer._build_messages("query", conversation=[own_resp])
    history_msg = messages[1]  # after system, before user query
    assert history_msg["role"] == "assistant"
    assert "Root cause is X." in history_msg["content"]


def test_build_messages_other_agents_mapped_to_user(analyzer):
    from backend.agents.orchestrator import AgentResponse
    other_resp = AgentResponse(
        agent="finder",
        contribution_type="NEW_EVIDENCE",
        contribution_detail="found case",
        addressed_to="@analyzer",
        content="Case #0847 pattern found.",
    )
    messages = analyzer._build_messages("query", conversation=[other_resp])
    history_msg = messages[1]
    assert history_msg["role"] == "user"
    assert "[FINDER]" in history_msg["content"]


def test_build_messages_includes_context_as_system_message(analyzer):
    messages = analyzer._build_messages("query", conversation=[], context="Previous case notes.")
    system_messages = [m for m in messages if m["role"] == "system"]
    context_msgs = [m for m in system_messages if "Previous case notes." in m["content"]]
    assert len(context_msgs) == 1


# ---------------------------------------------------------------------------
# BaseAgent.role is set on concrete subclasses
# ---------------------------------------------------------------------------

def test_analyzer_role_is_analyzer():
    from backend.agents.analyzer import AnalyzerAgent
    assert AnalyzerAgent.role == "analyzer"


def test_finder_role_is_finder():
    from backend.agents.finder import FinderAgent
    assert FinderAgent.role == "finder"


def test_reviewer_role_is_reviewer():
    from backend.agents.reviewer import ReviewerAgent
    assert ReviewerAgent.role == "reviewer"
