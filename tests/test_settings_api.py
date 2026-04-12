"""Tests for settings API endpoints."""

import json
import shutil
import pytest
from pathlib import Path
from httpx import ASGITransport, AsyncClient

from backend.main import create_app


@pytest.fixture
def settings_app(tmp_path, monkeypatch):
    """Create app with temp config + data dirs to avoid modifying real files."""
    # Copy real config files into a separate tmp config dir
    real_config = Path(__file__).parent.parent / "data" / "config"
    tmp_config = tmp_path / "settings_config"
    shutil.copytree(real_config, tmp_config)
    tmp_data = tmp_path / "data"
    tmp_data.mkdir(exist_ok=True)
    (tmp_data / "sqlite").mkdir(exist_ok=True)
    (tmp_data / "chroma_db").mkdir(exist_ok=True)

    import backend.config
    monkeypatch.setattr(backend.config, "CONFIG_DIR", tmp_config)
    monkeypatch.setattr(backend.config, "DATA_DIR", tmp_data)

    return create_app()


@pytest.fixture
async def settings_client(settings_app):
    transport = ASGITransport(app=settings_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_get_settings_models(settings_client):
    resp = await settings_client.get("/api/settings/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "roles" in data
    assert "providers" in data
    # Keys should be redacted (no api_key_env)
    for p in data["providers"].values():
        assert "api_key_env" not in p


async def test_update_settings_models(settings_client, settings_app):
    # Get current
    resp = await settings_client.get("/api/settings/models")
    current = resp.json()

    # Update roles
    new_roles = dict(current["roles"])
    new_roles["analyzer"]["model"] = "test-model-updated"

    resp = await settings_client.put("/api/settings/models", json={"roles": new_roles})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify in-memory update
    assert settings_app.state.models_config["roles"]["analyzer"]["model"] == "test-model-updated"


async def test_get_vectordb_stats(settings_client):
    resp = await settings_client.get("/api/settings/vectordb/stats")
    assert resp.status_code == 200
    data = resp.json()
    # Should have entries for all collection names (may be 0)
    assert "case_records" in data
    assert "traces" in data
    assert "weekly" in data
    assert "manuals" in data


async def test_update_dropdowns(settings_client, settings_app):
    new_dropdowns = {
        "accounts": {
            "TEST": {
                "tools": {
                    "TOOL1": {"components": ["C1", "C2"]}
                }
            }
        }
    }
    resp = await settings_client.put("/api/settings/dropdowns", json=new_dropdowns)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify in-memory update
    assert "TEST" in settings_app.state.dropdowns_config["accounts"]


async def test_test_connection_unknown_provider(settings_client):
    resp = await settings_client.post(
        "/api/settings/test-connection",
        json={"provider": "unknown", "api_key": "sk-test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "Unknown provider" in data["error"]
