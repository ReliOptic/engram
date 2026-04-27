"""Tests for OpenRouterClient and OpenAIClient — key validation and model prefix stripping."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.utils.openrouter import OpenRouterClient
from backend.utils.openai_client import OpenAIClient


# ---------------------------------------------------------------------------
# OpenRouterClient
# ---------------------------------------------------------------------------

async def test_openrouter_empty_api_key_raises_before_http_call():
    """No HTTP request must be made when the API key is empty."""
    client = OpenRouterClient(api_key="")
    with patch("httpx.AsyncClient") as mock_cls:
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            await client.complete("gemini/model", [{"role": "user", "content": "hi"}])
        mock_cls.assert_not_called()


async def test_openrouter_none_api_key_raises():
    client = OpenRouterClient.__new__(OpenRouterClient)
    client.api_key = None
    client.base_url = "https://openrouter.ai/api/v1"
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        await client.complete("gemini/model", [])


async def test_openrouter_complete_sends_model_in_payload():
    """The model name passed to complete() is forwarded to the API payload."""
    client = OpenRouterClient(api_key="test-key")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "answer"}}],
        "model": "google/gemini-2.0-flash-lite-001",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await client.complete(
            "google/gemini-2.0-flash-lite-001",
            [{"role": "user", "content": "test"}],
        )

    _, call_kwargs = mock_http.post.call_args
    assert call_kwargs["json"]["model"] == "google/gemini-2.0-flash-lite-001"
    assert result.content == "answer"


async def test_openrouter_complete_returns_llm_response_with_usage():
    client = OpenRouterClient(api_key="test-key")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "ok"}}],
        "model": "google/gemini-2.0-flash-lite-001",
        "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await client.complete(
            "google/gemini-2.0-flash-lite-001", [{"role": "user", "content": "test"}]
        )

    assert result.prompt_tokens == 50
    assert result.completion_tokens == 30
    assert result.total_tokens == 80
    assert result.provider == "openrouter"


# ---------------------------------------------------------------------------
# OpenAIClient
# ---------------------------------------------------------------------------

async def test_openai_empty_api_key_raises_before_api_call():
    client = OpenAIClient(api_key="")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        await client.complete("gpt-4o", [{"role": "user", "content": "hi"}])


async def test_openai_strips_openai_prefix_from_model():
    """Model name "openai/gpt-5.4" should be sent as "gpt-5.4" to the SDK."""
    client = OpenAIClient(api_key="test-key")

    mock_choice = MagicMock()
    mock_choice.message.content = "response"
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 5
    mock_usage.completion_tokens = 10
    mock_usage.total_tokens = 15
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage = mock_usage
    mock_completion.model = "gpt-5.4"

    client._client.chat.completions.create = AsyncMock(return_value=mock_completion)

    await client.complete("openai/gpt-5.4", [{"role": "user", "content": "test"}])

    call_kwargs = client._client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-5.4"


async def test_openai_model_without_prefix_passed_unchanged():
    client = OpenAIClient(api_key="test-key")

    mock_choice = MagicMock()
    mock_choice.message.content = "response"
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 5
    mock_usage.completion_tokens = 10
    mock_usage.total_tokens = 15
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage = mock_usage
    mock_completion.model = "gpt-4o"

    client._client.chat.completions.create = AsyncMock(return_value=mock_completion)

    await client.complete("gpt-4o", [{"role": "user", "content": "test"}])

    call_kwargs = client._client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o"


async def test_openai_complete_returns_llm_response():
    client = OpenAIClient(api_key="test-key")

    mock_choice = MagicMock()
    mock_choice.message.content = "gpt answer"
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 20
    mock_usage.completion_tokens = 10
    mock_usage.total_tokens = 30
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage = mock_usage
    mock_completion.model = "gpt-5.4"

    client._client.chat.completions.create = AsyncMock(return_value=mock_completion)

    result = await client.complete("gpt-5.4", [{"role": "user", "content": "test"}])

    assert result.content == "gpt answer"
    assert result.provider == "openai"
    assert result.prompt_tokens == 20
    assert result.completion_tokens == 10
