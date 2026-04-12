"""Tests for Knowledge API endpoints (/api/knowledge/stats and /api/knowledge/search).

These tests use the conftest `client` fixture (backed by the autouse `mock_env` fixture)
so that the same `DATA_DIR` patch is used by both the test setup and the endpoint handler.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app


async def test_knowledge_stats_empty(client):
    """Stats endpoint returns valid structure with zeros when DB is empty."""
    resp = await client.get("/api/knowledge/stats")
    assert resp.status_code == 200
    data = resp.json()

    assert "collections" in data
    assert "total_chunks" in data
    assert "cases" in data
    assert "total" in data["cases"]
    assert "recent_7d" in data["cases"]

    assert data["cases"]["total"] == 0
    assert data["cases"]["recent_7d"] == 0
    assert data["total_chunks"] == 0
    # All collection counts should be zero
    for count in data["collections"].values():
        assert count == 0


async def test_knowledge_stats_with_cases(client):
    """Stats endpoint reflects cases inserted directly into SQLite.

    We write the case using the same DATA_DIR the endpoint will read from
    (both patched by the autouse mock_env fixture via conftest).
    """
    import backend.config as _cfg
    from backend.knowledge.database import ZemasDB

    db_path = _cfg.DATA_DIR / "sqlite" / "zemas.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = ZemasDB(str(db_path))
    db.create_case(
        case_id="TEST-001",
        account="SEC",
        tool="PROVE",
        component="InCell",
        title="Test case for stats",
    )
    db.close()

    resp = await client.get("/api/knowledge/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cases"]["total"] == 1
    assert data["cases"]["recent_7d"] == 1


async def test_knowledge_search_empty(client):
    """Search endpoint returns empty results when collection has no data."""
    resp = await client.get("/api/knowledge/search?q=test&collection=manuals")
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "count" in data
    assert data["results"] == []
    assert data["count"] == 0


async def test_knowledge_search_with_error_handling(client):
    """Search with an unknown collection returns a graceful error response (no 500)."""
    resp = await client.get(
        "/api/knowledge/search?q=anything&collection=nonexistent_collection"
    )
    # Endpoint catches all exceptions and returns a valid JSON body — never a 500
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "count" in data
    assert data["results"] == []
    assert data["count"] == 0
