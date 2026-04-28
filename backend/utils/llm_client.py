"""Provider-agnostic LLM client for Engram.

Dispatches to OpenRouter or OpenAI based on role → provider mapping
in models.json. Tracks token usage and estimates cost.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.utils.openrouter import OpenRouterClient
from backend.utils.openai_client import OpenAIClient


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    content: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class LLMClient:
    """Provider-agnostic LLM dispatcher with cost tracking.

    Routes requests to the correct provider based on role configuration
    in models.json. All agent code uses this class — never calls
    providers directly.
    """

    def __init__(self, config: dict):
        self._config = config
        self._openrouter = OpenRouterClient()
        self._openai = OpenAIClient()
        self._cost_table = config.get("cost_per_million_tokens", {})
        self.last_response: LLMResponse | None = None

    async def complete(
        self,
        role: str,
        messages: list[dict],
        **kwargs,
    ) -> LLMResponse:
        """Dispatch a chat completion to the provider configured for this role.

        Args:
            role: Agent role name (e.g., "analyzer", "finder", "reviewer").
            messages: OpenAI-format message list.
            **kwargs: Additional params passed to provider (temperature, etc.).

        Returns:
            LLMResponse with content, token counts, and estimated cost.
        """
        role_config = self._config["roles"][role]
        provider = role_config["provider"]
        model = role_config["model"]

        # Merge role defaults with explicit kwargs
        call_kwargs = {
            "max_tokens": role_config.get("max_tokens", 4096),
            "temperature": role_config.get("temperature", 0.3),
        }
        call_kwargs.update(kwargs)

        if provider == "openrouter":
            response = await self._openrouter.complete(model, messages, **call_kwargs)
        elif provider == "openai":
            response = await self._openai.complete(model, messages, **call_kwargs)
        else:
            raise ValueError(f"Unknown provider: {provider}")

        # Calculate cost
        response.estimated_cost_usd = self.estimate_cost(
            model, response.prompt_tokens, response.completion_tokens
        )

        self.last_response = response
        return response

    def estimate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Estimate cost in USD based on token counts and model pricing.

        Args:
            model: Model identifier (e.g., "google/gemini-3.1-flash-lite-preview").
            prompt_tokens: Number of input tokens.
            completion_tokens: Number of output tokens.

        Returns:
            Estimated cost in USD.
        """
        pricing = self._cost_table.get(model, {"input": 0.0, "output": 0.0})
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost
