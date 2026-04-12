"""Shared test fixtures for Engram test suite."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Test config directory with real config files
TEST_ROOT = Path(__file__).parent.parent
TEST_CONFIG_DIR = TEST_ROOT / "data" / "config"


@pytest.fixture(autouse=True)
def mock_env(monkeypatch, tmp_path):
    """Patch environment variables and module-level paths for all tests."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("ENGRAM_CONFIG_DIR", str(TEST_CONFIG_DIR))
    tmp_data = tmp_path / "data"
    monkeypatch.setenv("ENGRAM_DATA_DIR", str(tmp_data))
    # Create data subdirs in tmp
    (tmp_data / "chroma_db").mkdir(parents=True, exist_ok=True)
    (tmp_data / "sqlite").mkdir(parents=True, exist_ok=True)
    # Patch module-level Path objects so they point to tmp dirs
    import backend.config
    monkeypatch.setattr(backend.config, "CONFIG_DIR", TEST_CONFIG_DIR)
    monkeypatch.setattr(backend.config, "DATA_DIR", tmp_data)


@pytest.fixture(autouse=True)
def fake_embedding_function(monkeypatch):
    """Replace the default VectorDB embedding function with a fake.

    Every Engram collection (case_records, traces, weekly, manuals) routes
    embeddings through ``backend.knowledge.vectordb._default_embedding_function``.
    Patching it here means no test ever hits real OpenRouter — the fake
    function produces deterministic 1536-dim vectors from a SHA-256 hash.
    """
    from backend.knowledge import vectordb as _vectordb
    from backend.knowledge.embedding_function import FakeEmbeddingFunction

    fake = FakeEmbeddingFunction()
    monkeypatch.setattr(_vectordb, "_default_embedding_function", lambda: fake)


@pytest.fixture
def app():
    """Create a fresh FastAPI app instance."""
    # Re-import to pick up patched env vars
    from backend.main import create_app
    return create_app()


@pytest.fixture
async def client(app):
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_llm_response():
    """Factory for mock LLM responses."""
    def _make(content="Test response", prompt_tokens=10, completion_tokens=20):
        return {
            "content": content,
            "model": "google/gemini-3.1-flash-lite-preview",
            "provider": "openrouter",
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "estimated_cost_usd": 0.0,
        }
    return _make


@pytest.fixture
def models_config():
    """Load real models.json for tests."""
    with open(TEST_CONFIG_DIR / "models.json") as f:
        return json.load(f)


@pytest.fixture
def dropdowns_config():
    """Load real dropdowns.json for tests."""
    with open(TEST_CONFIG_DIR / "dropdowns.json") as f:
        return json.load(f)
