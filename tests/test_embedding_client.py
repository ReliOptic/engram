"""Tests for SyncOpenRouterEmbeddingClient.

Covers:
- embed([]) short-circuits to an empty result with no HTTP call
- embed_single returns a single vector
- 200 OK parses embeddings + usage and preserves index ordering
- 429 retries up to max_retries, honours retry-after header, then succeeds
- 5xx retries with exponential backoff then succeeds
- Persistent 5xx exhausts retries → EmbeddingError
- Non-retryable HTTP errors (e.g. 401) raise EmbeddingError immediately
"""

from __future__ import annotations

import httpx
import pytest

from backend.utils.embedding_client import (
    EmbeddingError,
    EmbeddingResult,
    SyncOpenRouterEmbeddingClient,
)


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Skip wall-clock waits during retry/backoff so tests stay fast."""
    monkeypatch.setattr(
        "backend.utils.embedding_client.time.sleep", lambda *_: None
    )


def _embed_payload(vectors: list[list[float]], pt: int = 5) -> dict:
    return {
        "model": "openai/text-embedding-3-small",
        "data": [
            {"index": i, "embedding": v} for i, v in enumerate(vectors)
        ],
        "usage": {"prompt_tokens": pt, "total_tokens": pt},
    }


def _make_client(monkeypatch, handler) -> SyncOpenRouterEmbeddingClient:
    """Build a client with httpx.MockTransport patched in."""
    transport = httpx.MockTransport(handler)
    real_sync = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_sync(transport=transport)

    monkeypatch.setattr("backend.utils.embedding_client.httpx.Client", fake_client)
    return SyncOpenRouterEmbeddingClient(
        api_key="test-key",
        base_url="https://example.test/v1",
        max_retries=3,
        retry_backoff=0.01,
    )


# --------------------------------------------------------------------------- #
# Short-circuit + parsing
# --------------------------------------------------------------------------- #

def test_embed_empty_input_short_circuits():
    """No HTTP call for empty input — returns empty result with model+0 tokens."""
    client = SyncOpenRouterEmbeddingClient(api_key="x")
    result = client.embed([])
    assert isinstance(result, EmbeddingResult)
    assert result.embeddings == []
    assert result.prompt_tokens == 0
    assert result.total_tokens == 0


def test_embed_success_parses_payload(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=_embed_payload(
            [[0.1, 0.2], [0.3, 0.4]], pt=7
        ))

    client = _make_client(monkeypatch, handler)
    result = client.embed(["hello", "world"])

    assert captured["url"].endswith("/embeddings")
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert result.embeddings == [[0.1, 0.2], [0.3, 0.4]]
    assert result.prompt_tokens == 7
    assert result.total_tokens == 7


def test_embed_sorts_response_by_index(monkeypatch):
    """OpenRouter is allowed to return data items out-of-order — we re-sort."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "model": "m",
            "data": [
                {"index": 1, "embedding": [9.9]},
                {"index": 0, "embedding": [0.0]},
            ],
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        })

    client = _make_client(monkeypatch, handler)
    result = client.embed(["a", "b"])
    assert result.embeddings == [[0.0], [9.9]]


def test_embed_single_returns_first_vector(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_embed_payload([[1.0, 2.0, 3.0]]))

    client = _make_client(monkeypatch, handler)
    vec = client.embed_single("text")
    assert vec == [1.0, 2.0, 3.0]


# --------------------------------------------------------------------------- #
# Retry behaviour
# --------------------------------------------------------------------------- #

def test_embed_retries_on_429_then_succeeds(monkeypatch):
    """First call returns 429, second returns 200 — result is parsed normally."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, text="rate limited")
        return httpx.Response(200, json=_embed_payload([[0.5]]))

    client = _make_client(monkeypatch, handler)
    result = client.embed(["x"])
    assert calls["n"] == 2
    assert result.embeddings == [[0.5]]


def test_embed_retries_on_5xx_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json=_embed_payload([[1.0]]))

    client = _make_client(monkeypatch, handler)
    result = client.embed(["x"])
    assert calls["n"] == 2
    assert result.embeddings == [[1.0]]


def test_embed_persistent_5xx_exhausts_retries(monkeypatch):
    """If every attempt returns 5xx, raise EmbeddingError after max_retries."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    client = _make_client(monkeypatch, handler)
    with pytest.raises(EmbeddingError):
        client.embed(["x"])
    assert calls["n"] == 3  # max_retries=3


def test_embed_4xx_raises_immediately_no_retry(monkeypatch):
    """A 401/403 is not retryable — wrap in EmbeddingError on first try."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="unauthorized")

    client = _make_client(monkeypatch, handler)
    with pytest.raises(EmbeddingError, match="401"):
        client.embed(["x"])
    assert calls["n"] == 1  # no retries on 4xx (other than 429)


def test_embed_timeout_retries(monkeypatch):
    """httpx.TimeoutException triggers retry; subsequent success returns result."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json=_embed_payload([[0.0]]))

    client = _make_client(monkeypatch, handler)
    result = client.embed(["x"])
    assert calls["n"] == 2
    assert result.embeddings == [[0.0]]


def test_embed_429_honours_retry_after_header(monkeypatch):
    """Logs the retry-after-derived wait but does not exceed max_retries."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "0"}, text="rl")
        return httpx.Response(200, json=_embed_payload([[2.0]]))

    client = _make_client(monkeypatch, handler)
    result = client.embed(["x"])
    assert calls["n"] == 3
    assert result.embeddings == [[2.0]]
