"""Tests for DB Builder configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from db_builder.config import (
    DBBuilderConfig,
    EmbeddingConfig,
    load_models_json,
    _extract_embedding_config,
)


class TestLoadModelsJson:
    def test_loads_valid_file(self, engram_config_dir: Path):
        models = load_models_json(engram_config_dir)
        assert "providers" in models
        assert "roles" in models
        assert "embedding" in models["roles"]

    def test_raises_on_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="models.json not found"):
            load_models_json(tmp_path)


class TestExtractEmbeddingConfig:
    def test_extracts_model_and_provider(self, engram_config_dir: Path):
        models = load_models_json(engram_config_dir)
        emb = _extract_embedding_config(models)

        assert emb.model == "openai/text-embedding-3-small"
        assert emb.provider == "openrouter"
        assert emb.base_url == "https://openrouter.ai/api/v1"
        assert emb.api_key_env == "OPENROUTER_API_KEY"
        assert emb.cost_per_million_input == 0.02

    def test_raises_on_missing_embedding_role(self, tmp_path: Path):
        models = {"providers": {}, "roles": {}}
        (tmp_path / "models.json").write_text(json.dumps(models))
        with pytest.raises(KeyError, match="No 'embedding' role"):
            _extract_embedding_config(models)

    def test_raises_on_missing_provider(self, tmp_path: Path):
        models = {
            "providers": {},
            "roles": {"embedding": {"provider": "missing", "model": "x"}},
        }
        with pytest.raises(KeyError, match="Provider 'missing' not found"):
            _extract_embedding_config(models)


class TestDBBuilderConfig:
    def test_default_values(self):
        cfg = DBBuilderConfig()
        assert cfg.max_chunk_tokens == 1024
        assert cfg.min_chunk_tokens == 50
        assert cfg.chunk_overlap_tokens == 100
        assert cfg.quality_threshold == 0.5
        assert cfg.embedding_batch_size == 100
        assert cfg.embedding_dimension == 1536
        assert cfg.max_concurrent_files == 4
        assert cfg.checkpoint_interval == 100

    def test_custom_paths(self, tmp_path: Path):
        cfg = DBBuilderConfig(
            raw_data_dir=tmp_path / "raw",
            chromadb_dir=tmp_path / "chroma",
            db_path=tmp_path / "test.db",
            engram_config_dir=tmp_path / "config",
        )
        assert cfg.raw_data_dir == tmp_path / "raw"
        assert cfg.chromadb_dir == tmp_path / "chroma"


class TestEmbeddingConfig:
    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")
        emb = EmbeddingConfig(
            model="openai/text-embedding-3-small",
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
        )
        assert emb.api_key == "test-key-123"

    def test_api_key_raises_when_missing(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        emb = EmbeddingConfig(
            model="openai/text-embedding-3-small",
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
        )
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY is not set"):
            _ = emb.api_key
