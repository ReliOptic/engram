"""Tests for tacit knowledge extraction from conversations.

Spec reference: scaffolding-plan-v3.md Section 5.1 delta, Section 11.2
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.knowledge.tacit_extractor import TacitExtractor


@pytest.fixture
def extractor():
    mock_llm = AsyncMock()
    return TacitExtractor(llm_client=mock_llm)


def _make_llm_response(content: str):
    """Create mock LLMResponse."""
    from backend.utils.llm_client import LLMResponse
    return LLMResponse(
        content=content,
        model="test",
        provider="test",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_usd=0.0,
    )


async def test_extracts_field_decision(extractor):
    """'시간 부족으로 TIS 스킵' → field_decision 타입 추출."""
    llm_output = json.dumps([
        {
            "signal": "SE가 PM 중 시간 압박으로 TIS recalibration을 스킵함",
            "type": "field_decision",
            "source_speaker": "kiwon",
            "context": "post_PM, SEC PROVE LE#3",
            "confidence": 0.85,
            "related_procedure": "Ch.8.3 TIS recalibration",
        }
    ])
    extractor._llm.complete = AsyncMock(return_value=_make_llm_response(llm_output))

    conversation_text = (
        "[USER] SEC PROVE LE#3에서 PM 후 offset 3nm 발생\n"
        "[ANALYZER] TIS recalibration 확인 필요\n"
        "[USER] 시간 부족으로 TIS 스킵했음"
    )
    signals = await extractor.extract(conversation_text)

    assert len(signals) == 1
    assert signals[0]["type"] == "field_decision"
    assert "TIS" in signals[0]["signal"]


async def test_ignores_standard_procedure(extractor):
    """매뉴얼 표준 절차 → 추출하지 않음."""
    # LLM returns empty array for standard procedures
    extractor._llm.complete = AsyncMock(return_value=_make_llm_response("[]"))

    conversation_text = (
        "[USER] PROVE InCell DB registration 에러\n"
        "[ANALYZER] Ch.8.3 step 4-7 따라 calibration 진행\n"
        "[REVIEWER] 표준 절차 맞습니다"
    )
    signals = await extractor.extract(conversation_text)
    assert len(signals) == 0


async def test_ignores_greetings(extractor):
    """인사말, 확인 요청 → 추출하지 않음."""
    extractor._llm.complete = AsyncMock(return_value=_make_llm_response("[]"))

    conversation_text = (
        "[USER] 안녕하세요, 확인 부탁드립니다\n"
        "[ANALYZER] 안녕하세요, 살펴보겠습니다"
    )
    signals = await extractor.extract(conversation_text)
    assert len(signals) == 0


async def test_empty_when_no_tacit(extractor):
    """암묘지 없는 대화 → 빈 배열 반환."""
    extractor._llm.complete = AsyncMock(return_value=_make_llm_response("[]"))

    signals = await extractor.extract("Simple standard troubleshooting conversation.")
    assert signals == []


async def test_customer_specific_detected(extractor):
    """고객사별 특수 조건 → customer_specific 타입."""
    llm_output = json.dumps([
        {
            "signal": "SEC에서는 300모드보다 200모드를 선호함",
            "type": "customer_specific",
            "source_speaker": "kiwon",
            "context": "SEC PROVE setup preference",
            "confidence": 0.78,
            "related_procedure": "",
        }
    ])
    extractor._llm.complete = AsyncMock(return_value=_make_llm_response(llm_output))

    conversation_text = "[USER] SEC에서는 300모드 대신 200모드로 세팅해야 합니다"
    signals = await extractor.extract(conversation_text)

    assert len(signals) == 1
    assert signals[0]["type"] == "customer_specific"
    assert "SEC" in signals[0]["signal"]
