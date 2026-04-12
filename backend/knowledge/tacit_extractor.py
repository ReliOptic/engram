"""Tacit knowledge extractor — finds implicit expertise in conversations.

On case close, runs an LLM prompt to extract field-level knowledge
that isn't in manuals: workarounds, customer preferences, tool quirks, etc.

Spec reference: scaffolding-plan-v3.md Section 5.1 delta
"""

from __future__ import annotations

import json

from backend.utils.llm_client import LLMClient

TACIT_EXTRACTION_PROMPT = """
아래는 ZEISS EUV 장비 기술지원 에이전트와 AE/SE 사이의 대화 기록입니다.

이 대화에서 **매뉴얼이나 공식 문서에는 없지만, 현장 경험에서만 알 수 있는
판단, 절차, 맥락**을 추출해주세요.

추출 기준:
- 공식 절차에서 벗어난 현장 판단 (예: "시간 부족으로 TIS 스킵")
- 고객사별 특수 조건 (예: "SEC에서는 이 모드를 선호함")
- 에러 코드의 비공식 해석 (예: "PRV-4412는 보통 PM 후에 나오는데...")
- 장비 간 개체차이 (예: "m106은 stage drift가 좀 있음")
- 이전 경험 기반 우선순위 판단 (예: "이건 TIS부터 해봐야 돼")

추출하지 말 것:
- 매뉴얼에 명시된 표준 절차
- 인사말, 확인 요청 등 업무 외 대화
- 에이전트가 VectorDB/wiki에서 검색해온 정보 (이미 기록됨)

JSON 배열로 반환:
[
    {
        "signal": "SE가 PM 중 시간 압박으로 TIS recalibration을 스킵함",
        "type": "field_decision",
        "source_speaker": "kiwon",
        "context": "post_PM, SEC PROVE LE#3",
        "confidence": 0.85,
        "related_procedure": "Ch.8.3 TIS recalibration"
    }
]

type은 다음 중 하나: field_decision | customer_specific | unofficial_interpretation | tool_specific | priority_judgment

대화에서 암묘지가 발견되지 않으면 빈 배열 []을 반환하세요.

대화 기록:
{conversation_text}
""".strip()


class TacitExtractor:
    """Extract tacit knowledge signals from agent conversations."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    async def extract(self, conversation_text: str) -> list[dict]:
        """Run LLM extraction on a conversation transcript.

        Args:
            conversation_text: Full conversation as text.

        Returns:
            List of tacit signal dicts, or empty list if none found.
        """
        prompt = TACIT_EXTRACTION_PROMPT.replace("{conversation_text}", conversation_text)
        messages = [
            {"role": "system", "content": "You are a tacit knowledge extraction specialist."},
            {"role": "user", "content": prompt},
        ]

        response = await self._llm.complete("tacit_extraction", messages)

        return self._parse_signals(response.content)

    def _parse_signals(self, content: str) -> list[dict]:
        """Parse LLM output into signal list."""
        content = content.strip()

        # Handle markdown code blocks
        if "```" in content:
            import re
            match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
            if match:
                content = match.group(1)

        try:
            signals = json.loads(content)
            if isinstance(signals, list):
                return [s for s in signals if isinstance(s, dict) and s.get("signal")]
            return []
        except (json.JSONDecodeError, TypeError):
            return []

    async def extract_and_store(
        self,
        case_id: str,
        conversation_text: str,
        vectordb,
    ) -> list[dict]:
        """Extract tacit signals and store on the Type B trace chunk.

        Args:
            case_id: The case ID.
            conversation_text: Full conversation text.
            vectordb: VectorDB instance for metadata update.

        Returns:
            List of extracted signals.
        """
        signals = await self.extract(conversation_text)

        if signals:
            chunk = vectordb.get_by_id("traces", f"trace-{case_id}")
            if chunk:
                metadata = chunk["metadata"]
                metadata["tacit_signals"] = json.dumps(signals)
                vectordb.update_metadata("traces", f"trace-{case_id}", metadata)

        return signals
