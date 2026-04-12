"""DB Builder configuration loader.

Reads settings from environment variables and ENGRAM models.json.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _project_root() -> Path:
    """DB_Builder/ directory.

    In portable/frozen mode (PyInstaller), uses the directory containing
    the executable. Otherwise uses the source tree root.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller: exe directory
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def _default_engram_config_dir() -> Path:
    # In portable mode, look for config/ next to the app first
    local_config = _project_root() / "config"
    if local_config.exists():
        return local_config
    # Fallback: ENGRAM project's config dir
    return _project_root().parent / "data" / "config"


def _default_engram_data_dir() -> Path:
    # In portable mode, use data/ next to the app
    local_data = _project_root() / "data"
    if local_data.exists():
        return local_data
    return _project_root().parent / "data"


@dataclass
class EmbeddingConfig:
    """Embedding settings extracted from models.json."""

    model: str
    provider: str
    base_url: str
    api_key_env: str
    cost_per_million_input: float = 0.02

    @property
    def api_key(self) -> str:
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise ValueError(
                f"Environment variable {self.api_key_env} is not set. "
                "Add it to your .env file."
            )
        return key


@dataclass
class DBBuilderConfig:
    """Global configuration for DB Builder."""

    # --- Paths ---
    raw_data_dir: Path = field(default_factory=lambda: _project_root() / "data" / "raw")
    chromadb_dir: Path = field(default_factory=lambda: _default_engram_data_dir() / "chroma_db")
    db_path: Path = field(default_factory=lambda: _project_root() / "data" / "db_builder.db")
    engram_config_dir: Path = field(default_factory=_default_engram_config_dir)

    # --- Embedding (populated from models.json) ---
    embedding: EmbeddingConfig | None = None

    # --- Chunking ---
    max_chunk_tokens: int = 1024
    min_chunk_tokens: int = 50
    chunk_overlap_tokens: int = 100

    # --- Quality ---
    quality_threshold: float = 0.5

    # --- Processing ---
    embedding_batch_size: int = 100
    embedding_dimension: int = 1536
    max_concurrent_files: int = 4
    checkpoint_interval: int = 100


def load_models_json(config_dir: Path) -> dict:
    """Load and return the raw models.json dict."""
    models_path = config_dir / "models.json"
    if not models_path.exists():
        raise FileNotFoundError(
            f"models.json not found at {models_path}. "
            "Set ENGRAM_CONFIG_DIR to the correct path."
        )
    return json.loads(models_path.read_text(encoding="utf-8"))


def _extract_embedding_config(models: dict) -> EmbeddingConfig:
    """Extract embedding settings from models.json."""
    roles = models.get("roles", {})
    if "embedding" not in roles:
        raise KeyError("No 'embedding' role defined in models.json")

    role_cfg = roles["embedding"]
    provider_name = role_cfg["provider"]

    providers = models.get("providers", {})
    if provider_name not in providers:
        raise KeyError(f"Provider '{provider_name}' not found in models.json providers")

    provider_cfg = providers[provider_name]
    cost_table = models.get("cost_per_million_tokens", {})
    model_name = role_cfg["model"]
    cost_input = cost_table.get(model_name, {}).get("input", 0.0)

    return EmbeddingConfig(
        model=model_name,
        provider=provider_name,
        base_url=provider_cfg["base_url"],
        api_key_env=provider_cfg["env_key"],
        cost_per_million_input=cost_input,
    )


def _default_embedding_config() -> EmbeddingConfig:
    """Fallback embedding config when models.json is not available."""
    return EmbeddingConfig(
        model="openai/text-embedding-3-small",
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        cost_per_million_input=0.02,
    )


def load_config() -> DBBuilderConfig:
    """Load full configuration from env + models.json.

    In portable mode (no ENGRAM project), creates a local models.json
    with default embedding config if one doesn't exist.
    """
    root = _project_root()
    load_dotenv(root / ".env")

    engram_config_dir = Path(
        os.getenv("ENGRAM_CONFIG_DIR", str(_default_engram_config_dir()))
    )
    engram_data_dir = Path(
        os.getenv("ENGRAM_DATA_DIR", str(_default_engram_data_dir()))
    )

    # Try to load models.json; fall back to defaults for portable mode
    try:
        models = load_models_json(engram_config_dir)
        embedding = _extract_embedding_config(models)
    except (FileNotFoundError, KeyError):
        # Portable mode: no ENGRAM project available
        # Create local config/ with default models.json
        local_config = root / "config"
        local_config.mkdir(parents=True, exist_ok=True)
        models_path = local_config / "models.json"
        if not models_path.exists():
            default_models = {
                "providers": {
                    "openrouter": {
                        "base_url": "https://openrouter.ai/api/v1",
                        "env_key": "OPENROUTER_API_KEY",
                    }
                },
                "roles": {
                    "embedding": {
                        "provider": "openrouter",
                        "model": "openai/text-embedding-3-small",
                    }
                },
                "cost_per_million_tokens": {
                    "openai/text-embedding-3-small": {"input": 0.02, "output": 0.0}
                },
            }
            models_path.write_text(
                json.dumps(default_models, indent=2), encoding="utf-8"
            )
        embedding = _default_embedding_config()
        engram_config_dir = local_config

    raw_data_dir = Path(os.getenv("DB_BUILDER_RAW_DIR", str(root / "data" / "raw")))
    raw_data_dir.mkdir(parents=True, exist_ok=True)

    db_dir = Path(os.getenv("DB_BUILDER_DB_PATH", str(root / "data" / "db_builder.db")))
    db_dir.parent.mkdir(parents=True, exist_ok=True)

    chromadb_dir = engram_data_dir / "chroma_db"
    chromadb_dir.mkdir(parents=True, exist_ok=True)

    return DBBuilderConfig(
        raw_data_dir=raw_data_dir,
        chromadb_dir=chromadb_dir,
        db_path=db_dir,
        engram_config_dir=engram_config_dir,
        embedding=embedding,
    )
