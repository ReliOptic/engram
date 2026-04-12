"""ZEMAS configuration loader.

Loads .env for secrets, models.json for model registry,
dropdowns.json for UI hierarchy. Supports ZEMAS_CONFIG_DIR
override for test isolation.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = Path(os.getenv("ZEMAS_CONFIG_DIR", PROJECT_ROOT / "data" / "config"))
DATA_DIR = Path(os.getenv("ZEMAS_DATA_DIR", PROJECT_ROOT / "data"))

# API keys
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# App
VERSION = "0.2.0"

# Sync (optional — empty means standalone mode, no sync)
SYNC_SERVER_URL = os.getenv("SYNC_SERVER_URL", "")
SYNC_DEVICE_NAME = os.getenv("SYNC_DEVICE_NAME", os.getenv("COMPUTERNAME", "unknown"))


def load_models_config() -> dict:
    """Load model registry from models.json."""
    config_path = CONFIG_DIR / "models.json"
    with open(config_path) as f:
        return json.load(f)


def load_dropdowns_config() -> dict:
    """Load UI dropdown hierarchy from dropdowns.json."""
    config_path = CONFIG_DIR / "dropdowns.json"
    with open(config_path) as f:
        return json.load(f)


def get_role_config(role: str) -> dict:
    """Get provider + model config for a specific agent role."""
    models = load_models_config()
    if role not in models["roles"]:
        raise ValueError(f"Unknown role: {role}. Available: {list(models['roles'].keys())}")
    return models["roles"][role]


def get_provider_config(provider: str) -> dict:
    """Get base URL and env key for a provider."""
    models = load_models_config()
    if provider not in models["providers"]:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(models['providers'].keys())}")
    return models["providers"][provider]


def get_cost_table() -> dict:
    """Get cost-per-million-tokens table."""
    models = load_models_config()
    return models.get("cost_per_million_tokens", {})
