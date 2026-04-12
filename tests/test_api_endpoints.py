"""TDD tests for Phase 0-A: FastAPI backend foundation.

These tests define the contract that the implementation must satisfy.
Written BEFORE the implementation code per TDD principle.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# --- Health Check ---

async def test_health_check(client):
    """GET /health returns 200 + {"status": "ok"}."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


async def test_health_check_includes_version(client):
    """Health response includes a version string."""
    resp = await client.get("/health")
    data = resp.json()
    assert "version" in data
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0


# --- WebSocket ---

async def test_websocket_user_message(app):
    """WebSocket /ws accepts user_message and returns status_update."""
    from starlette.testclient import TestClient

    msg = json.dumps({"type": "user_message", "payload": {"text": "hello Engram", "silo": {}}})
    with TestClient(app) as tc:
        with tc.websocket_connect("/ws") as ws:
            ws.send_text(msg)
            data = json.loads(ws.receive_text())
            assert data["type"] == "status_update"
            assert data["payload"]["status"] == "processing"


async def test_websocket_json_message(app):
    """WebSocket /ws echoes back non-user_message JSON."""
    from starlette.testclient import TestClient

    msg = json.dumps({"type": "ping", "payload": "test"})
    with TestClient(app) as tc:
        with tc.websocket_connect("/ws") as ws:
            ws.send_text(msg)
            data = ws.receive_text()
            assert json.loads(data) == {"type": "ping", "payload": "test"}


# --- CORS ---

async def test_cors_headers_present(client):
    """OPTIONS request returns CORS headers allowing all origins (dev mode)."""
    resp = await client.options(
        "/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert resp.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")


# --- Config Loading ---

async def test_config_loads_models_json(client):
    """GET /api/config/models returns model registry."""
    resp = await client.get("/api/config/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "roles" in data
    assert "analyzer" in data["roles"]
    assert "provider" in data["roles"]["analyzer"]


async def test_config_loads_dropdowns_json(client):
    """GET /api/config/dropdowns returns account hierarchy."""
    resp = await client.get("/api/config/dropdowns")
    assert resp.status_code == 200
    data = resp.json()
    assert "accounts" in data
    assert len(data["accounts"]) >= 1


async def test_dropdowns_cascade(client):
    """Account → Tool → Component hierarchy is navigable."""
    resp = await client.get("/api/config/dropdowns")
    data = resp.json()
    first_account = list(data["accounts"].keys())[0]
    account = data["accounts"][first_account]
    assert "tools" in account
    first_tool = list(account["tools"].keys())[0]
    tool = account["tools"][first_tool]
    assert "components" in tool
    assert len(tool["components"]) >= 1


# --- LLM Client ---

async def test_llm_client_dispatches_to_openrouter():
    """LLMClient routes 'openrouter' provider correctly."""
    from backend.utils.llm_client import LLMClient, LLMResponse
    from backend.config import load_models_config

    config = load_models_config()
    llm = LLMClient(config)

    mock_response = LLMResponse(
        content="test",
        model="google/gemini-3.1-flash-lite-preview",
        provider="openrouter",
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        estimated_cost_usd=0.0,
    )

    with patch.object(llm._openrouter, "complete", new_callable=AsyncMock, return_value=mock_response):
        result = await llm.complete("analyzer", [{"role": "user", "content": "test"}])
        assert result.provider == "openrouter"
        assert result.content == "test"


async def test_llm_client_dispatches_to_openai():
    """LLMClient routes 'openai' provider correctly."""
    from backend.utils.llm_client import LLMClient, LLMResponse
    from backend.config import load_models_config

    config = load_models_config()
    # Temporarily override analyzer to use openai
    config["roles"]["analyzer"]["provider"] = "openai"
    config["roles"]["analyzer"]["model"] = "openai/gpt-5.4"

    llm = LLMClient(config)

    mock_response = LLMResponse(
        content="openai test",
        model="openai/gpt-5.4",
        provider="openai",
        prompt_tokens=15,
        completion_tokens=25,
        total_tokens=40,
        estimated_cost_usd=0.0001,
    )

    with patch.object(llm._openai, "complete", new_callable=AsyncMock, return_value=mock_response):
        result = await llm.complete("analyzer", [{"role": "user", "content": "test"}])
        assert result.provider == "openai"
        assert result.content == "openai test"


async def test_llm_client_tracks_tokens():
    """LLMResponse includes token counts."""
    from backend.utils.llm_client import LLMResponse

    resp = LLMResponse(
        content="hello",
        model="test-model",
        provider="openrouter",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_usd=0.0,
    )
    assert resp.prompt_tokens == 100
    assert resp.completion_tokens == 50
    assert resp.total_tokens == 150


async def test_llm_client_tracks_cost():
    """LLMClient estimates cost based on model pricing."""
    from backend.utils.llm_client import LLMClient
    from backend.config import load_models_config

    config = load_models_config()
    llm = LLMClient(config)

    cost = llm.estimate_cost("google/gemini-3.1-flash-lite-preview", prompt_tokens=1000, completion_tokens=500)
    # Gemini Flash Lite is free tier
    assert cost == 0.0

    cost = llm.estimate_cost("openai/gpt-5.4", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    # $2.50/M input + $10.00/M output
    assert cost == pytest.approx(12.50, abs=0.01)
