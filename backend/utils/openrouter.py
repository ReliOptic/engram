"""OpenRouter API client for ZEMAS.

Handles HTTP calls to OpenRouter's chat completions endpoint.
Supports all models available on OpenRouter (Gemini, Claude, etc.).
"""

from __future__ import annotations

import httpx

from backend.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL


class OpenRouterClient:
    """Async client for OpenRouter chat completions."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or OPENROUTER_API_KEY
        self.base_url = base_url or OPENROUTER_BASE_URL

    async def complete(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.3,
        **kwargs,
    ) -> "LLMResponse":
        """Call OpenRouter chat completions and return standardized response."""
        from backend.utils.llm_client import LLMResponse

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://zemas.zeiss.local",
            "X-Title": "ZEMAS",
        }

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", model),
            provider="openrouter",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            estimated_cost_usd=0.0,  # Calculated by LLMClient
        )
