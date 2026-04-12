"""TDD tests for contribution validation logic.

Spec reference: scaffolding-plan-v3.md Section 3.1 delta, Section 11.2
Tests written BEFORE implementation.
"""

import pytest

from backend.agents.orchestrator import (
    CONTRIBUTION_TYPES,
    AgentResponse,
    validate_contribution,
)


def _make_response(
    agent: str = "analyzer",
    contribution_type: str = "NEW_EVIDENCE",
    contribution_detail: str = "Found error code PRV-4412 in manual Ch.8.3",
    addressed_to: str = "@You",
    content: str = "Based on error PRV-4412, this indicates TIS misalignment post-PM.",
    is_pass: bool = False,
) -> AgentResponse:
    """Helper to build AgentResponse for tests."""
    return AgentResponse(
        agent=agent,
        contribution_type="PASS" if is_pass else contribution_type,
        contribution_detail="" if is_pass else contribution_detail,
        addressed_to=addressed_to,
        content="PASS" if is_pass else content,
    )


def test_new_evidence_with_source():
    """새 source_id를 포함한 응답 → 기여 인정."""
    history = []  # Empty history — everything is new
    response = _make_response(
        contribution_type="NEW_EVIDENCE",
        contribution_detail="Found Case #0847 with similar PRV-4412 pattern",
        content="Case #0847 showed TIS recalibration resolved the offset. Source: case_record_0847.",
    )
    assert validate_contribution(response, history) is True


def test_new_evidence_without_new_info():
    """이미 대화에 있는 정보 반복 → 기여 불인정."""
    existing_content = "TIS recalibration is needed based on PRV-4412."
    history = [
        _make_response(
            agent="analyzer",
            content=existing_content,
            contribution_detail="TIS recalibration needed",
        )
    ]
    # Repeats the same info already in history
    response = _make_response(
        agent="finder",
        contribution_type="NEW_EVIDENCE",
        contribution_detail="TIS recalibration needed",
        content="I also think TIS recalibration is needed based on PRV-4412.",
    )
    assert validate_contribution(response, history) is False


def test_counter_with_reasoning():
    """다른 에이전트 의견에 근거 있는 반론 → 기여 인정."""
    history = [
        _make_response(
            agent="analyzer",
            content="Root cause is TIS misalignment at 78% probability.",
        )
    ]
    response = _make_response(
        agent="finder",
        contribution_type="COUNTER",
        contribution_detail="Challenging TIS-only hypothesis — ref mark data suggests otherwise",
        addressed_to="@Analyzer",
        content="Case #0847 showed ref mark degradation caused similar offset. "
                "TIS probability should be lower, ref mark higher.",
    )
    assert validate_contribution(response, history) is True


def test_bare_agreement_rejected():
    """'동의합니다' → PASS로 재분류."""
    history = [
        _make_response(agent="analyzer", content="TIS recalibration is the solution.")
    ]
    response = _make_response(
        agent="reviewer",
        contribution_type="NEW_EVIDENCE",
        contribution_detail="Agreement with Analyzer",
        content="I agree with @Analyzer. TIS recalibration is correct.",
    )
    assert validate_contribution(response, history) is False


def test_revise_changes_previous():
    """자신의 이전 발언을 수정 → 기여 인정."""
    history = [
        _make_response(
            agent="analyzer",
            content="Root cause: TIS 78%, ref mark 15%.",
            contribution_detail="Initial root cause analysis",
        )
    ]
    response = _make_response(
        agent="analyzer",
        contribution_type="REVISE",
        contribution_detail="Updating probabilities based on Finder's Case #0847 data",
        content="Revised: TIS 65%, ref mark 25%. Finder's case data changes the distribution.",
    )
    assert validate_contribution(response, history) is True
