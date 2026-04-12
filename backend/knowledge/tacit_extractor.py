"""Tacit knowledge extractor — finds implicit expertise in conversations.

On case close, runs an LLM prompt to extract field-level knowledge
that isn't in manuals: workarounds, customer preferences, tool quirks, etc.

Spec reference: scaffolding-plan-v3.md Section 5.1 delta
"""

from __future__ import annotations

import json

from backend.utils.llm_client import LLMClient

TACIT_EXTRACTION_PROMPT = """
Below is a conversation between support agents and a user.

Extract **tacit knowledge** — insights that are NOT in official documentation
but come from field experience, practical judgment, or contextual awareness.

Extraction criteria:
- Field decisions that deviate from standard procedure (e.g., "skipped step X due to time constraints")
- Client-specific conditions (e.g., "this client prefers mode Y")
- Unofficial interpretation of error codes (e.g., "error X usually appears after maintenance")
- Equipment/system-specific quirks (e.g., "unit #106 has some drift")
- Experience-based priority judgments (e.g., "always check X before Y")

Do NOT extract:
- Standard procedures documented in manuals
- Greetings, confirmations, or non-technical conversation
- Information the agent retrieved from the knowledge base (already recorded)

Return a JSON array:
[
    {
        "signal": "Engineer skipped recalibration due to time pressure",
        "type": "field_decision",
        "source_speaker": "user",
        "context": "post-maintenance, Client A Product A",
        "confidence": 0.85,
        "related_procedure": "Section 8.3 Recalibration"
    }
]

type must be one of: field_decision | customer_specific | unofficial_interpretation | tool_specific | priority_judgment

If no tacit knowledge is found, return an empty array [].

Conversation:
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
