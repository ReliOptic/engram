"""OpenRouter embedding API client.

Standalone client that calls the OpenRouter /embeddings endpoint.
Reads model config from ZEMAS models.json via DBBuilderConfig.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result from a single embedding API call."""

    embeddings: list[list[float]]
    model: str
    prompt_tokens: int
    total_tokens: int


class EmbeddingClient:
    """Calls OpenRouter's embedding endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "openai/text-embedding-3-small",
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._client = httpx.Client(timeout=self.timeout)

    def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed a batch of texts. Retries on transient errors."""
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": texts,
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self._client.post(url, json=payload, headers=headers)

                if response.status_code == 429:
                    # Rate limited — wait and retry
                    retry_after = float(response.headers.get("retry-after", self.retry_backoff))
                    wait = max(retry_after, self.retry_backoff * (2 ** attempt))
                    logger.warning(
                        "Rate limited (429). Waiting %.1fs (attempt %d/%d)",
                        wait, attempt + 1, self.max_retries,
                    )
                    time.sleep(wait)
                    continue

                if response.status_code >= 500:
                    wait = self.retry_backoff * (2 ** attempt)
                    logger.warning(
                        "Server error %d. Waiting %.1fs (attempt %d/%d)",
                        response.status_code, wait, attempt + 1, self.max_retries,
                    )
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                data = response.json()
                return self._parse_response(data)

            except httpx.TimeoutException as e:
                last_error = e
                wait = self.retry_backoff * (2 ** attempt)
                logger.warning(
                    "Timeout. Waiting %.1fs (attempt %d/%d)",
                    wait, attempt + 1, self.max_retries,
                )
                time.sleep(wait)

            except httpx.HTTPStatusError as e:
                # Non-retryable client error (4xx except 429)
                raise EmbeddingError(
                    f"API error {e.response.status_code}: {e.response.text}"
                ) from e

        raise EmbeddingError(
            f"Failed after {self.max_retries} retries: {last_error}"
        )

    def embed_single(self, text: str) -> list[float]:
        """Embed a single text. Convenience wrapper."""
        result = self.embed([text])
        return result.embeddings[0]

    def _parse_response(self, data: dict) -> EmbeddingResult:
        """Parse the OpenAI-compatible embedding response."""
        embeddings_data = data.get("data", [])
        # Sort by index to ensure correct ordering
        embeddings_data.sort(key=lambda x: x.get("index", 0))
        embeddings = [item["embedding"] for item in embeddings_data]

        usage = data.get("usage", {})
        return EmbeddingResult(
            embeddings=embeddings,
            model=data.get("model", self.model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> EmbeddingClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()


class EmbeddingError(Exception):
    """Raised when embedding API call fails."""
