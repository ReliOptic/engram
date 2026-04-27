"""Tests for backend.config — model registry / dropdown loaders + role lookup.

Covers:
- load_models_config / load_dropdowns_config read from CONFIG_DIR
- get_role_config returns the right role block; raises on unknown role
- get_provider_config returns provider dict; raises on unknown provider
- get_cost_table returns the pricing dict (empty dict if absent)
- ENGRAM_CONFIG_DIR env var is honoured at module import (smoke check
  via the autouse `mock_env` fixture which already sets it to TEST_CONFIG_DIR)
"""

from __future__ import annotations

import json

import pytest

import backend.config as cfg


def test_load_models_config_returns_full_registry():
    data = cfg.load_models_config()
    # Top-level shape from data/config/models.json
    assert "providers" in data
    assert "roles" in data
    assert "cost_per_million_tokens" in data
    # Sanity on roles
    assert "analyzer" in data["roles"]
    assert data["roles"]["analyzer"]["provider"] in {"openrouter", "openai"}


def test_load_dropdowns_config_reads_file():
    data = cfg.load_dropdowns_config()
    assert isinstance(data, dict)
    assert data  # non-empty


# --- get_role_config ------------------------------------------------------- #

def test_get_role_config_known_role():
    role = cfg.get_role_config("analyzer")
    assert role["provider"] in {"openrouter", "openai"}
    assert "model" in role


def test_get_role_config_unknown_raises():
    with pytest.raises(ValueError, match="Unknown role"):
        cfg.get_role_config("nonexistent_role_xyz")


# --- get_provider_config --------------------------------------------------- #

def test_get_provider_config_known_provider():
    provider = cfg.get_provider_config("openrouter")
    assert "base_url" in provider
    assert "env_key" in provider


def test_get_provider_config_unknown_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        cfg.get_provider_config("anthropic")


# --- get_cost_table ------------------------------------------------------- #

def test_get_cost_table_returns_pricing_dict():
    table = cfg.get_cost_table()
    assert isinstance(table, dict)
    # Every entry must have input + output keys
    for model, pricing in table.items():
        assert "input" in pricing, f"{model} missing input"
        assert "output" in pricing, f"{model} missing output"


# --- env override behaviour ------------------------------------------------ #

def test_config_dir_overridden_by_env(tmp_path, monkeypatch):
    """CONFIG_DIR is overridable via ENGRAM_CONFIG_DIR.

    The conftest already sets ENGRAM_CONFIG_DIR to the test data dir; this
    test confirms that loaders honour the patched cfg.CONFIG_DIR.
    """
    fake_dir = tmp_path / "alt_config"
    fake_dir.mkdir()
    fake_models = {
        "providers": {"openrouter": {"base_url": "x", "env_key": "X"}},
        "roles": {"analyzer": {"provider": "openrouter", "model": "fake-model"}},
        "cost_per_million_tokens": {},
    }
    (fake_dir / "models.json").write_text(json.dumps(fake_models))
    (fake_dir / "dropdowns.json").write_text(json.dumps({"foo": ["bar"]}))

    monkeypatch.setattr(cfg, "CONFIG_DIR", fake_dir)

    assert cfg.load_models_config() == fake_models
    assert cfg.load_dropdowns_config() == {"foo": ["bar"]}
    assert cfg.get_role_config("analyzer")["model"] == "fake-model"


def test_load_models_missing_file_raises(tmp_path, monkeypatch):
    """Missing models.json surfaces an OSError rather than silent empty config."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setattr(cfg, "CONFIG_DIR", empty_dir)
    with pytest.raises((FileNotFoundError, OSError)):
        cfg.load_models_config()


def test_version_constant_is_semver_like():
    """VERSION is a non-empty string — used by /health endpoint."""
    assert isinstance(cfg.VERSION, str) and cfg.VERSION
    parts = cfg.VERSION.split(".")
    assert len(parts) >= 2
    # major + minor are numeric
    assert all(p.isdigit() for p in parts[:2])
