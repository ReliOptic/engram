"""LLM Wiki Enrichment — Karpathy Wiki LLM pattern.

After chunking, LLM enriches each chunk with:
- title: concise descriptive title
- summary: 1-2 sentence summary
- keywords: searchable keywords
- cross_references: related topics/sections
- tool_family: PROVE/AIMS/WLCD/FAVOR detection
- language: detected language

Also maintains a wiki index (index.md) of all ingested documents.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

ENRICH_PROMPT = """You are a technical documentation analyst for ZEISS EUV lithography equipment (PROVE, AIMS, WLCD, FAVOR).

Analyze this text chunk and return a JSON object with these fields:
- "title": concise descriptive title (max 80 chars)
- "summary": 1-2 sentence summary of what this chunk is about
- "keywords": list of 3-8 searchable keywords (English, technical terms)
- "cross_references": list of related topics, procedures, or sections mentioned (e.g. "TIS recalibration", "Chapter 8.3")
- "tool_family": which tool this relates to: "PROVE", "AIMS", "WLCD", "FAVOR", or "general"
- "language": detected language: "en", "de", "ko", or "mixed"
- "is_safety_critical": true if this contains WARNING, CAUTION, DANGER, or safety procedures

Return ONLY valid JSON, no markdown fencing, no explanation.

Text chunk:
---
{text}
---"""

INDEX_PROMPT = """You are maintaining a wiki index for ZEISS EUV equipment documentation.

Given these document summaries, generate a markdown index page organized by topic.
Group by tool_family (PROVE, AIMS, General), then by topic area.
Each entry should be: `- **{title}** — {summary} [source: {source_file}]`

Documents:
{documents}

Generate the index in markdown format. Start with `# ZEMAS Knowledge Base Index`."""


@dataclass
class EnrichmentResult:
    """LLM-generated metadata for a chunk."""

    title: str = ""
    summary: str = ""
    keywords: list[str] | None = None
    cross_references: list[str] | None = None
    tool_family: str = "general"
    language: str = "en"
    is_safety_critical: bool = False
    tokens_used: int = 0


class LLMEnricher:
    """Enriches chunks using LLM (via OpenRouter).

    Uses a cost-effective model (Gemini Flash Lite) for enrichment,
    not the embedding model.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "google/gemini-2.0-flash-lite-001",
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = httpx.Client(timeout=self.timeout)

    def enrich_chunk(self, text: str) -> EnrichmentResult:
        """Send chunk text to LLM for enrichment. Returns structured metadata."""
        prompt = ENRICH_PROMPT.format(text=text[:3000])

        try:
            response = self._call_llm(prompt)
            return self._parse_enrichment(response)
        except Exception as e:
            logger.warning("Enrichment failed: %s", e)
            return EnrichmentResult()

    def generate_index(self, documents: list[dict], output_path: Path) -> str:
        """Generate wiki index.md from document summaries."""
        doc_text = "\n".join(
            f"- source: {d.get('source_file', '?')}, "
            f"tool: {d.get('tool_family', '?')}, "
            f"title: {d.get('title', '?')}, "
            f"summary: {d.get('summary', '?')}"
            for d in documents
        )

        prompt = INDEX_PROMPT.format(documents=doc_text)
        try:
            index_md = self._call_llm(prompt)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(index_md, encoding="utf-8")
            logger.info("Wiki index updated: %s", output_path)
            return index_md
        except Exception as e:
            logger.error("Index generation failed: %s", e)
            return ""

    def _call_llm(self, prompt: str) -> str:
        """Call OpenRouter chat completion."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 500,
        }

        resp = self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        content = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)

        return content

    def _parse_enrichment(self, response: str) -> EnrichmentResult:
        """Parse LLM JSON response into EnrichmentResult."""
        # Strip markdown fencing if present
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse enrichment JSON: %s", text[:200])
            return EnrichmentResult()

        return EnrichmentResult(
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            keywords=data.get("keywords"),
            cross_references=data.get("cross_references"),
            tool_family=data.get("tool_family", "general"),
            language=data.get("language", "en"),
            is_safety_critical=data.get("is_safety_critical", False),
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
