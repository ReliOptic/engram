"""Tests for LLMClient — cost estimation and provider routing."""

import pytest
from unittest.mock import AsyncMock

from backend.utils.llm_client import LLMClient, LLMResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIG = {
    "roles": {
        "analyzer": {
            "provider": "openrouter",
            "model": "google/gemini-2.0-flash-lite-001",
            "max_tokens": 4096,
            "temperature": 0.3,
        },
        "reviewer": {
            "provider": "openai",
            "model": "openai/gpt-5.4",
            "max_tokens": 2048,
            "temperature": 0.2,
        },
        "bad_provider_role": {
            "provider": "anthropic",
            "model": "claude-x",
            "max_tokens": 4096,
            "temperature": 0.3,
        },
    },
    "cost_per_million_tokens": {
        "google/gemini-2.0-flash-lite-001": {"input": 0.0, "output": 0.0},
        "openai/gpt-5.4": {"input": 2.5, "output": 10.0},
    },
}


def _fake_response(**overrides) -> LLMResponse:
    base = dict(
        content="ok",
        model="google/gemini-2.0-flash-lite-001",
        provider="openrouter",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_usd=0.0,
    )
    base.update(overrides)
    return LLMResponse(**base)


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------

def test_estimate_cost_free_model_returns_zero():
    client = LLMClient(_CONFIG)
    assert client.estimate_cost("google/gemini-2.0-flash-lite-001", 1_000_000, 1_000_000) == 0.0


def test_estimate_cost_paid_model():
    client = LLMClient(_CONFIG)
    # 1M prompt tokens @ $2.50/M + 1M completion tokens @ $10.00/M = $12.50
    cost = client.estimate_cost("openai/gpt-5.4", 1_000_000, 1_000_000)
    assert cost == pytest.approx(12.50)


def test_estimate_cost_partial_tokens():
    client = LLMClient(_CONFIG)
    # 500K @ $2.50/M = $1.25  +  200K @ $10.00/M = $2.00  → $3.25
    cost = client.estimate_cost("openai/gpt-5.4", 500_000, 200_000)
    assert cost == pytest.approx(3.25)


def test_estimate_cost_unknown_model_returns_zero():
    client = LLMClient(_CONFIG)
    assert client.estimate_cost("unknown/mystery-model", 1_000_000, 1_000_000) == 0.0


def test_estimate_cost_zero_tokens():
    client = LLMClient(_CONFIG)
    assert client.estimate_cost("openai/gpt-5.4", 0, 0) == 0.0


# ---------------------------------------------------------------------------
# complete() — provider routing
# ---------------------------------------------------------------------------

async def test_complete_routes_to_openrouter_for_openrouter_role():
    client = LLMClient(_CONFIG)
    expected = _fake_response(provider="openrouter")
    client._openrouter.complete = AsyncMock(return_value=expected)
    client._openai.complete = AsyncMock(side_effect=AssertionError("openai must not be called"))

    result = await client.complete("analyzer", [{"role": "user", "content": "test"}])

    client._openrouter.complete.assert_called_once()
    assert result.provider == "openrouter"


async def test_complete_routes_to_openai_for_openai_role():
    client = LLMClient(_CONFIG)
    expected = _fake_response(provider="openai", model="openai/gpt-5.4")
    client._openai.complete = AsyncMock(return_value=expected)
    client._openrouter.complete = AsyncMock(side_effect=AssertionError("openrouter must not be called"))

    result = await client.complete("reviewer", [{"role": "user", "content": "test"}])

    client._openai.complete.assert_called_once()
    assert result.provider == "openai"


async def test_complete_unknown_provider_raises_value_error():
    client = LLMClient(_CONFIG)
    with pytest.raises(ValueError, match="Unknown provider"):
        await client.complete("bad_provider_role", [])


async def test_complete_sets_estimated_cost_from_config_model():
    """Cost is calculated using the role's configured model, not response.model."""
    client = LLMClient(_CONFIG)
    # analyzer → "google/gemini-2.0-flash-lite-001" (free model)
    raw = _fake_response(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    client._openrouter.complete = AsyncMock(return_value=raw)

    result = await client.complete("analyzer", [])

    assert result.estimated_cost_usd == 0.0


async def test_complete_merges_role_defaults_with_explicit_kwargs():
    """Explicit kwargs passed to complete() override role defaults."""
    client = LLMClient(_CONFIG)
    raw = _fake_response()
    client._openrouter.complete = AsyncMock(return_value=raw)

    await client.complete("analyzer", [], temperature=0.99)

    call_kwargs = client._openrouter.complete.call_args.kwargs
    assert call_kwargs["temperature"] == pytest.approx(0.99)


async def test_complete_passes_role_default_max_tokens():
    client = LLMClient(_CONFIG)
    raw = _fake_response()
    client._openrouter.complete = AsyncMock(return_value=raw)

    await client.complete("analyzer", [])

    call_kwargs = client._openrouter.complete.call_args.kwargs
    assert call_kwargs["max_tokens"] == 4096  # from _CONFIG roles.analyzer.max_tokens
