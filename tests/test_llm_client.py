"""Tests for the provider-agnostic LLM client and HTTP provider clients.

Covers:
- LLMClient.complete() dispatch by role → provider
- LLMClient.estimate_cost() math (incl. unknown-model fallback)
- OpenRouterClient request/response handling via mocked transport
- OpenAIClient request/response handling via mocked AsyncOpenAI
- Error paths: unknown provider, HTTP 5xx surfaced, malformed payload
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.utils.llm_client import LLMClient, LLMResponse
from backend.utils.openai_client import OpenAIClient
from backend.utils.openrouter import OpenRouterClient


# --------------------------------------------------------------------------- #
# LLMClient — dispatch and cost
# --------------------------------------------------------------------------- #

@pytest.fixture
def base_config():
    return {
        "roles": {
            "analyzer": {
                "provider": "openrouter",
                "model": "google/gemini-2.0-flash-lite-001",
                "max_tokens": 512,
                "temperature": 0.4,
            },
            "writer": {
                "provider": "openai",
                "model": "openai/gpt-5.4",
                "max_tokens": 1024,
                "temperature": 0.1,
            },
            "broken": {
                "provider": "anthropic",  # unknown
                "model": "claude-x",
            },
        },
        "cost_per_million_tokens": {
            "google/gemini-2.0-flash-lite-001": {"input": 0.0, "output": 0.0},
            "openai/gpt-5.4": {"input": 2.5, "output": 10.0},
        },
    }


def _llm_response(model="m", provider="openrouter", pt=10, ct=20):
    return LLMResponse(
        content="hi",
        model=model,
        provider=provider,
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=pt + ct,
        estimated_cost_usd=0.0,
    )


async def test_complete_routes_to_openrouter(base_config):
    """Role with provider=openrouter dispatches to OpenRouterClient."""
    client = LLMClient(base_config)
    client._openrouter = AsyncMock()
    client._openrouter.complete.return_value = _llm_response(
        model="google/gemini-2.0-flash-lite-001"
    )
    client._openai = AsyncMock()

    resp = await client.complete("analyzer", [{"role": "user", "content": "hi"}])

    client._openrouter.complete.assert_awaited_once()
    client._openai.complete.assert_not_awaited()

    # Role defaults forwarded
    call_kwargs = client._openrouter.complete.await_args.kwargs
    assert call_kwargs["max_tokens"] == 512
    assert call_kwargs["temperature"] == 0.4

    assert resp.provider == "openrouter"


async def test_complete_routes_to_openai(base_config):
    """Role with provider=openai dispatches to OpenAIClient."""
    client = LLMClient(base_config)
    client._openrouter = AsyncMock()
    client._openai = AsyncMock()
    client._openai.complete.return_value = _llm_response(
        model="openai/gpt-5.4", provider="openai", pt=1000, ct=500
    )

    resp = await client.complete("writer", [{"role": "user", "content": "hi"}])

    client._openai.complete.assert_awaited_once()
    client._openrouter.complete.assert_not_awaited()
    assert resp.provider == "openai"


async def test_complete_kwargs_override_role_defaults(base_config):
    """Explicit kwargs override role defaults from models.json."""
    client = LLMClient(base_config)
    client._openrouter = AsyncMock()
    client._openrouter.complete.return_value = _llm_response()

    await client.complete(
        "analyzer",
        [{"role": "user", "content": "hi"}],
        temperature=0.99,
        max_tokens=64,
    )

    call_kwargs = client._openrouter.complete.await_args.kwargs
    assert call_kwargs["temperature"] == 0.99
    assert call_kwargs["max_tokens"] == 64


async def test_complete_unknown_provider_raises(base_config):
    """An unknown provider in the role config raises ValueError."""
    client = LLMClient(base_config)
    with pytest.raises(ValueError, match="Unknown provider"):
        await client.complete("broken", [])


async def test_complete_attaches_estimated_cost(base_config):
    """LLMClient overwrites response.estimated_cost_usd using the cost table."""
    client = LLMClient(base_config)
    client._openai = AsyncMock()
    # 1M input @ $2.5 + 500k output @ $10 = $2.5 + $5 = $7.5
    client._openai.complete.return_value = _llm_response(
        model="openai/gpt-5.4", provider="openai",
        pt=1_000_000, ct=500_000,
    )

    resp = await client.complete("writer", [])

    assert resp.estimated_cost_usd == pytest.approx(2.5 + 5.0)


def test_estimate_cost_known_model(base_config):
    """Known model returns input*pricing + output*pricing."""
    client = LLMClient(base_config)
    cost = client.estimate_cost("openai/gpt-5.4", 100_000, 200_000)
    expected = (100_000 / 1_000_000) * 2.5 + (200_000 / 1_000_000) * 10.0
    assert cost == pytest.approx(expected)


def test_estimate_cost_unknown_model_returns_zero(base_config):
    """Unknown model falls back to zero pricing."""
    client = LLMClient(base_config)
    assert client.estimate_cost("unknown/model", 1_000_000, 1_000_000) == 0.0


def test_estimate_cost_zero_tokens_returns_zero(base_config):
    """Zero token counts yield zero cost regardless of model."""
    client = LLMClient(base_config)
    assert client.estimate_cost("openai/gpt-5.4", 0, 0) == 0.0


# --------------------------------------------------------------------------- #
# OpenRouterClient — HTTP behaviour via MockTransport
# --------------------------------------------------------------------------- #

def _openrouter_payload(content="hello", pt=11, ct=22):
    return {
        "id": "chatcmpl-1",
        "model": "google/gemini-2.0-flash-lite-001",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
        },
    }


async def test_openrouter_complete_success(monkeypatch):
    """OpenRouterClient parses a normal 200 response into LLMResponse."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_openrouter_payload(content="ok", pt=3, ct=5))

    transport = httpx.MockTransport(handler)

    # Patch httpx.AsyncClient so OpenRouterClient picks up our transport
    real_async_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=transport)

    monkeypatch.setattr("backend.utils.openrouter.httpx.AsyncClient", make_client)

    client = OpenRouterClient(api_key="rk-test", base_url="https://example.test/v1")
    resp = await client.complete(
        "google/gemini-2.0-flash-lite-001",
        [{"role": "user", "content": "hi"}],
        max_tokens=128,
        temperature=0.5,
    )

    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["authorization"] == "Bearer rk-test"
    assert captured["body"]["model"] == "google/gemini-2.0-flash-lite-001"
    assert captured["body"]["max_tokens"] == 128
    assert captured["body"]["temperature"] == 0.5

    assert resp.content == "ok"
    assert resp.prompt_tokens == 3
    assert resp.completion_tokens == 5
    assert resp.total_tokens == 8
    assert resp.provider == "openrouter"


async def test_openrouter_complete_http_500_raises(monkeypatch):
    """5xx errors propagate as httpx.HTTPStatusError (no silent fallback)."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=transport)

    monkeypatch.setattr("backend.utils.openrouter.httpx.AsyncClient", make_client)

    client = OpenRouterClient(api_key="x", base_url="https://example.test/v1")
    with pytest.raises(httpx.HTTPStatusError):
        await client.complete("model-x", [])


async def test_openrouter_missing_usage_defaults_zero(monkeypatch):
    """A response without `usage` reports zero tokens rather than crashing."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "model": "model-x",
            "choices": [{"message": {"content": "no usage"}}],
        })

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=transport)

    monkeypatch.setattr("backend.utils.openrouter.httpx.AsyncClient", make_client)

    client = OpenRouterClient(api_key="x", base_url="https://example.test/v1")
    resp = await client.complete("model-x", [])
    assert resp.prompt_tokens == 0
    assert resp.completion_tokens == 0
    assert resp.total_tokens == 0


# --------------------------------------------------------------------------- #
# OpenAIClient — happy path + provider prefix stripping
# --------------------------------------------------------------------------- #

class _FakeOpenAIChoice:
    def __init__(self, content):
        self.message = SimpleNamespace(content=content)


class _FakeOpenAIUsage:
    def __init__(self, pt, ct):
        self.prompt_tokens = pt
        self.completion_tokens = ct
        self.total_tokens = pt + ct


class _FakeOpenAIResponse:
    def __init__(self, model, content, pt, ct):
        self.model = model
        self.choices = [_FakeOpenAIChoice(content)]
        self.usage = _FakeOpenAIUsage(pt, ct)


async def test_openai_complete_strips_provider_prefix(monkeypatch):
    """A model id like 'openai/gpt-5.4' is sent to the SDK as 'gpt-5.4'."""
    captured = {}

    fake_async_openai = MagicMock()
    fake_async_openai.chat.completions.create = AsyncMock(
        return_value=_FakeOpenAIResponse("gpt-5.4", "hi", 4, 6)
    )

    def fake_constructor(api_key=None):
        return fake_async_openai

    monkeypatch.setattr(
        "backend.utils.openai_client.AsyncOpenAI", fake_constructor
    )

    client = OpenAIClient(api_key="sk-test")
    resp = await client.complete(
        "openai/gpt-5.4",
        [{"role": "user", "content": "hi"}],
        max_tokens=200,
        temperature=0.2,
    )

    fake_async_openai.chat.completions.create.assert_awaited_once()
    call_kwargs = fake_async_openai.chat.completions.create.await_args.kwargs
    assert call_kwargs["model"] == "gpt-5.4"  # prefix stripped
    assert call_kwargs["max_tokens"] == 200
    assert call_kwargs["temperature"] == 0.2

    assert resp.content == "hi"
    assert resp.provider == "openai"
    assert resp.prompt_tokens == 4
    assert resp.completion_tokens == 6


async def test_openai_complete_handles_none_content(monkeypatch):
    """OpenAI may return content=None for tool calls — we coerce to ''."""
    fake_async_openai = MagicMock()
    fake_async_openai.chat.completions.create = AsyncMock(
        return_value=_FakeOpenAIResponse("gpt-5.4", None, 1, 1)
    )
    monkeypatch.setattr(
        "backend.utils.openai_client.AsyncOpenAI",
        lambda api_key=None: fake_async_openai,
    )

    client = OpenAIClient(api_key="sk")
    resp = await client.complete("gpt-5.4", [])
    assert resp.content == ""


async def test_openai_complete_missing_usage(monkeypatch):
    """If SDK returns usage=None, token counts default to zero."""
    fake_async_openai = MagicMock()
    fake_resp = _FakeOpenAIResponse("gpt-5.4", "x", 0, 0)
    fake_resp.usage = None  # no usage block
    fake_async_openai.chat.completions.create = AsyncMock(return_value=fake_resp)
    monkeypatch.setattr(
        "backend.utils.openai_client.AsyncOpenAI",
        lambda api_key=None: fake_async_openai,
    )
    client = OpenAIClient(api_key="sk")
    resp = await client.complete("gpt-5.4", [])
    assert (resp.prompt_tokens, resp.completion_tokens, resp.total_tokens) == (0, 0, 0)
