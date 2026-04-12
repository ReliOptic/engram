"""Shared test fixtures for DB Builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


SAMPLE_MODELS_JSON = {
    "providers": {
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "env_key": "OPENROUTER_API_KEY",
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "env_key": "OPENAI_API_KEY",
        },
    },
    "roles": {
        "embedding": {
            "provider": "openrouter",
            "model": "openai/text-embedding-3-small",
        },
        "analyzer": {
            "provider": "openrouter",
            "model": "google/gemini-3.1-flash-lite-preview",
            "max_tokens": 4096,
            "temperature": 0.3,
        },
    },
    "cost_per_million_tokens": {
        "openai/text-embedding-3-small": {"input": 0.02, "output": 0.0},
        "google/gemini-3.1-flash-lite-preview": {"input": 0.0, "output": 0.0},
    },
}


@pytest.fixture
def engram_config_dir(tmp_path: Path) -> Path:
    """Create a temporary Engram config directory with models.json."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "models.json").write_text(
        json.dumps(SAMPLE_MODELS_JSON), encoding="utf-8"
    )
    return config_dir


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory structure."""
    data_dir = tmp_path / "data"
    for sub in ["raw/manuals", "raw/weekly_reports", "raw/sops", "raw/images", "raw/misc", "chroma_db"]:
        (data_dir / sub).mkdir(parents=True)
    return data_dir


@pytest.fixture
def sample_db_path(tmp_path: Path) -> Path:
    """Return a path for a temporary SQLite database."""
    return tmp_path / "test_db_builder.db"
