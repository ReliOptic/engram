"""Tests for SyncOpenRouterEmbeddingClient — embed, retry, parse."""

import pytest
from unittest.mock import MagicMock, patch

from backend.utils.embedding_client import (
    EmbeddingError,
    EmbeddingResult,
    SyncOpenRouterEmbeddingClient,
)


# ---------------------------------------------------------------------------
# embed — edge cases
# ---------------------------------------------------------------------------

def test_embed_empty_list_returns_empty_result():
    client = SyncOpenRouterEmbeddingClient(api_key="test-key")
    result = client.embed([])
    assert result.embeddings == []
    assert result.prompt_tokens == 0
    assert result.total_tokens == 0


def test_embed_empty_list_does_not_make_http_call():
    client = SyncOpenRouterEmbeddingClient(api_key="test-key")
    with patch("httpx.Client") as mock_cls:
        client.embed([])
        mock_cls.assert_not_called()


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

def test_parse_response_sorts_by_index():
    client = SyncOpenRouterEmbeddingClient(api_key="test-key")
    data = {
        "data": [
            {"index": 2, "embedding": [0.3]},
            {"index": 0, "embedding": [0.1]},
            {"index": 1, "embedding": [0.2]},
        ],
        "model": "openai/text-embedding-3-small",
        "usage": {"prompt_tokens": 3, "total_tokens": 3},
    }
    result = client._parse_response(data)
    assert result.embeddings == [[0.1], [0.2], [0.3]]


def test_parse_response_extracts_usage():
    client = SyncOpenRouterEmbeddingClient(api_key="test-key")
    data = {
        "data": [{"index": 0, "embedding": [0.5, 0.5]}],
        "model": "openai/text-embedding-3-small",
        "usage": {"prompt_tokens": 10, "total_tokens": 10},
    }
    result = client._parse_response(data)
    assert result.prompt_tokens == 10
    assert result.total_tokens == 10


def test_parse_response_uses_model_from_response():
    client = SyncOpenRouterEmbeddingClient(api_key="test-key")
    data = {
        "data": [{"index": 0, "embedding": [0.1]}],
        "model": "openai/text-embedding-3-large",
        "usage": {},
    }
    result = client._parse_response(data)
    assert result.model == "openai/text-embedding-3-large"


def test_parse_response_falls_back_to_client_model_when_missing():
    client = SyncOpenRouterEmbeddingClient(api_key="test-key", model="openai/text-embedding-3-small")
    data = {"data": [{"index": 0, "embedding": [0.1]}], "usage": {}}
    result = client._parse_response(data)
    assert result.model == "openai/text-embedding-3-small"


# ---------------------------------------------------------------------------
# embed_single
# ---------------------------------------------------------------------------

def test_embed_single_returns_flat_vector():
    client = SyncOpenRouterEmbeddingClient(api_key="test-key")
    mock_result = EmbeddingResult(
        embeddings=[[0.1, 0.2, 0.3]],
        model="test-model",
        prompt_tokens=1,
        total_tokens=1,
    )
    with patch.object(client, "embed", return_value=mock_result):
        vec = client.embed_single("hello world")
    assert vec == [0.1, 0.2, 0.3]


def test_embed_single_calls_embed_with_single_item_list():
    client = SyncOpenRouterEmbeddingClient(api_key="test-key")
    mock_result = EmbeddingResult(
        embeddings=[[0.5]], model="test", prompt_tokens=1, total_tokens=1
    )
    with patch.object(client, "embed", return_value=mock_result) as mock_embed:
        client.embed_single("test input")
    mock_embed.assert_called_once_with(["test input"])


# ---------------------------------------------------------------------------
# embed — HTTP error handling
# ---------------------------------------------------------------------------

def test_embed_raises_embedding_error_on_4xx_status():
    import httpx

    client = SyncOpenRouterEmbeddingClient(api_key="test-key", max_retries=1)

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    error = httpx.HTTPStatusError("401 Unauthorized", request=MagicMock(), response=mock_response)

    with patch("httpx.Client") as mock_cls:
        mock_http = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_http.post = MagicMock(side_effect=error)

        with pytest.raises(EmbeddingError, match="401"):
            client.embed(["test text"])


def test_embed_raises_embedding_error_after_all_retries_on_timeout():
    import httpx

    client = SyncOpenRouterEmbeddingClient(
        api_key="test-key", max_retries=2, retry_backoff=0.0
    )

    with patch("httpx.Client") as mock_cls:
        mock_http = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_http.post = MagicMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("time.sleep"):  # don't actually sleep in tests
            with pytest.raises(EmbeddingError, match="retries"):
                client.embed(["test text"])


def test_embed_succeeds_after_one_5xx_retry():
    """embed retries on 5xx and succeeds on the second attempt."""
    client = SyncOpenRouterEmbeddingClient(
        api_key="test-key", max_retries=3, retry_backoff=0.0
    )

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.json.return_value = {
        "data": [{"index": 0, "embedding": [0.1, 0.2]}],
        "model": "openai/text-embedding-3-small",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }

    server_error = MagicMock()
    server_error.status_code = 503

    def post_side_effect(*args, **kwargs):
        if post_side_effect.calls == 0:
            post_side_effect.calls += 1
            return server_error
        return ok_response

    post_side_effect.calls = 0

    with patch("httpx.Client") as mock_cls:
        mock_http = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_http.post = MagicMock(side_effect=post_side_effect)

        with patch("time.sleep"):
            result = client.embed(["test text"])

    assert result.embeddings == [[0.1, 0.2]]
