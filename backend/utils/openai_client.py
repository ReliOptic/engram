"""OpenAI API client for Engram.

Handles calls to OpenAI's chat completions via the official SDK.
Supports GPT-5.4, Codex, and other OpenAI models.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from backend.config import OPENAI_API_KEY


class OpenAIClient:
    """Async client for OpenAI chat completions."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or OPENAI_API_KEY
        self._client = AsyncOpenAI(api_key=self.api_key)

    async def complete(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.3,
        **kwargs,
    ) -> "LLMResponse":
        """Call OpenAI chat completions and return standardized response."""
        from backend.utils.llm_client import LLMResponse

        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Copy .env.example to .env and add your OpenAI API key."
            )

        # Strip provider prefix if present (e.g., "openai/gpt-5.4" → "gpt-5.4")
        if model.startswith("openai/"):
            model = model[len("openai/"):]

        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            provider="openai",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            estimated_cost_usd=0.0,  # Calculated by LLMClient
        )
