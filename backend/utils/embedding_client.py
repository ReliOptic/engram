"""Synchronous OpenRouter embedding client for ZEMAS.

Separate from ``openrouter.py`` (which is async chat completions) because
ChromaDB's ``EmbeddingFunction`` interface is synchronous — mixing async
into a sync interface via ``asyncio.run`` is fragile.

Mirror of DB Builder's ``embedding/client.py`` so both projects share the
same embedding semantics (model, base URL, retry policy).

Spec reference: scaffolding-plan-v3.md Section 5.1 (Embeddings)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from backend.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result from a single embedding API call."""

    embeddings: list[list[float]]
    model: str
    prompt_tokens: int
    total_tokens: int


class EmbeddingError(Exception):
    """Raised when embedding API call fails."""


class SyncOpenRouterEmbeddingClient:
    """Synchronous OpenRouter embeddings client with retry/backoff."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "openai/text-embedding-3-small",
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
    ):
        self.api_key = api_key or OPENROUTER_API_KEY
        self.base_url = (base_url or OPENROUTER_BASE_URL).rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

    def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed a batch of texts. Retries on 429/5xx."""
        if not texts:
            return EmbeddingResult(embeddings=[], model=self.model, prompt_tokens=0, total_tokens=0)

        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/zemas",
            "X-Title": "ZEMAS",
        }
        payload = {"model": self.model, "input": texts}

        last_error: Exception | None = None
        with httpx.Client(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    response = client.post(url, json=payload, headers=headers)

                    if response.status_code == 429:
                        wait = float(
                            response.headers.get(
                                "retry-after",
                                self.retry_backoff * (2 ** attempt),
                            )
                        )
                        logger.warning(
                            "Embedding rate limited (429). Waiting %.1fs (attempt %d/%d)",
                            wait, attempt + 1, self.max_retries,
                        )
                        time.sleep(wait)
                        continue

                    if response.status_code >= 500:
                        wait = self.retry_backoff * (2 ** attempt)
                        logger.warning(
                            "Embedding server error %d. Waiting %.1fs (attempt %d/%d)",
                            response.status_code, wait, attempt + 1, self.max_retries,
                        )
                        time.sleep(wait)
                        continue

                    response.raise_for_status()
                    return self._parse_response(response.json())

                except httpx.TimeoutException as e:
                    last_error = e
                    wait = self.retry_backoff * (2 ** attempt)
                    logger.warning(
                        "Embedding timeout. Waiting %.1fs (attempt %d/%d)",
                        wait, attempt + 1, self.max_retries,
                    )
                    time.sleep(wait)

                except httpx.HTTPStatusError as e:
                    raise EmbeddingError(
                        f"Embedding API error {e.response.status_code}: {e.response.text}"
                    ) from e

        raise EmbeddingError(
            f"Embedding failed after {self.max_retries} retries: {last_error}"
        )

    def embed_single(self, text: str) -> list[float]:
        """Convenience: embed a single text."""
        return self.embed([text]).embeddings[0]

    def _parse_response(self, data: dict) -> EmbeddingResult:
        """Parse OpenAI-compatible embedding response."""
        items = data.get("data", [])
        items.sort(key=lambda x: x.get("index", 0))
        embeddings = [item["embedding"] for item in items]
        usage = data.get("usage", {})
        return EmbeddingResult(
            embeddings=embeddings,
            model=data.get("model", self.model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )
