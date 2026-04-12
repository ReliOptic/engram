"""Tests for embedding client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from db_builder.embedding.client import EmbeddingClient, EmbeddingError, EmbeddingResult


def _make_response(
    status_code: int = 200,
    embeddings: list[list[float]] | None = None,
    prompt_tokens: int = 10,
    headers: dict | None = None,
    text: str = "",
):
    """Create a mock httpx.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.headers = headers or {}
    mock.text = text

    if embeddings is None:
        embeddings = [[0.1, 0.2, 0.3]]

    mock.json.return_value = {
        "data": [
            {"embedding": emb, "index": i}
            for i, emb in enumerate(embeddings)
        ],
        "model": "openai/text-embedding-3-small",
        "usage": {"prompt_tokens": prompt_tokens, "total_tokens": prompt_tokens},
    }
    mock.raise_for_status = MagicMock()
    return mock


class TestEmbeddingClient:
    def test_embed_single_text(self):
        client = EmbeddingClient(api_key="test-key", max_retries=1)
        mock_resp = _make_response(embeddings=[[0.1, 0.2, 0.3]])

        with patch.object(client._client, "post", return_value=mock_resp):
            result = client.embed(["hello world"])

        assert isinstance(result, EmbeddingResult)
        assert len(result.embeddings) == 1
        assert result.embeddings[0] == [0.1, 0.2, 0.3]
        assert result.model == "openai/text-embedding-3-small"
        assert result.prompt_tokens == 10

    def test_embed_batch(self):
        client = EmbeddingClient(api_key="test-key", max_retries=1)
        mock_resp = _make_response(
            embeddings=[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
            prompt_tokens=30,
        )

        with patch.object(client._client, "post", return_value=mock_resp):
            result = client.embed(["a", "b", "c"])

        assert len(result.embeddings) == 3
        assert result.embeddings[0] == [0.1, 0.2]
        assert result.embeddings[2] == [0.5, 0.6]
        assert result.prompt_tokens == 30

    def test_embed_single_convenience(self):
        client = EmbeddingClient(api_key="test-key", max_retries=1)
        mock_resp = _make_response(embeddings=[[0.5, 0.6, 0.7]])

        with patch.object(client._client, "post", return_value=mock_resp):
            vec = client.embed_single("test")

        assert vec == [0.5, 0.6, 0.7]

    def test_sends_correct_request(self):
        client = EmbeddingClient(
            api_key="sk-test-123",
            base_url="https://test.api/v1",
            model="custom-model",
            max_retries=1,
        )
        mock_resp = _make_response()

        with patch.object(client._client, "post", return_value=mock_resp) as mock_post:
            client.embed(["hello"])

        call_args = mock_post.call_args
        assert call_args[0][0] == "https://test.api/v1/embeddings"
        assert call_args[1]["headers"]["Authorization"] == "Bearer sk-test-123"
        assert call_args[1]["json"]["model"] == "custom-model"
        assert call_args[1]["json"]["input"] == ["hello"]

    def test_preserves_order_from_unordered_response(self):
        """API may return embeddings out of order; client sorts by index."""
        client = EmbeddingClient(api_key="test", max_retries=1)
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {
            "data": [
                {"embedding": [0.3], "index": 2},
                {"embedding": [0.1], "index": 0},
                {"embedding": [0.2], "index": 1},
            ],
            "model": "test",
            "usage": {"prompt_tokens": 5, "total_tokens": 5},
        }
        mock.raise_for_status = MagicMock()

        with patch.object(client._client, "post", return_value=mock):
            result = client.embed(["a", "b", "c"])

        assert result.embeddings == [[0.1], [0.2], [0.3]]

    def test_retry_on_429(self):
        client = EmbeddingClient(api_key="test", max_retries=3, retry_backoff=0.01)
        rate_limited = _make_response(status_code=429, text="rate limited")
        success = _make_response(embeddings=[[1.0, 2.0]])

        with patch.object(client._client, "post", side_effect=[rate_limited, success]):
            result = client.embed(["test"])

        assert result.embeddings[0] == [1.0, 2.0]

    def test_retry_on_500(self):
        client = EmbeddingClient(api_key="test", max_retries=3, retry_backoff=0.01)
        error_resp = _make_response(status_code=500)
        success = _make_response(embeddings=[[1.0]])

        with patch.object(client._client, "post", side_effect=[error_resp, success]):
            result = client.embed(["test"])

        assert len(result.embeddings) == 1

    def test_raises_after_max_retries(self):
        client = EmbeddingClient(api_key="test", max_retries=2, retry_backoff=0.01)
        error_resp = _make_response(status_code=500)

        with patch.object(client._client, "post", return_value=error_resp):
            with pytest.raises(EmbeddingError, match="Failed after 2 retries"):
                client.embed(["test"])

    def test_raises_on_4xx_immediately(self):
        client = EmbeddingClient(api_key="bad-key", max_retries=3, retry_backoff=0.01)
        error_resp = MagicMock()
        error_resp.status_code = 401
        error_resp.text = "Unauthorized"
        error_resp.raise_for_status.side_effect = __import__("httpx").HTTPStatusError(
            "401", request=MagicMock(), response=error_resp
        )

        with patch.object(client._client, "post", return_value=error_resp):
            with pytest.raises(EmbeddingError, match="API error 401"):
                client.embed(["test"])

    def test_context_manager(self):
        with EmbeddingClient(api_key="test") as client:
            assert client.api_key == "test"
        # No error on exit
