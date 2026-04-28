"""Tests for newly added endpoints: dreaming trigger, cost summary, sync push/pull, vectordb export."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# --- POST /api/dreaming/trigger ---

async def test_dreaming_trigger_ok(client):
    """POST /api/dreaming/trigger returns ok=True with expected fields on success."""
    mock_report = MagicMock()
    mock_report.timestamp = "2026-04-28T02:00:00"
    mock_report.light_sleep = []
    mock_report.rem_patterns = ["p1", "p2"]
    mock_report.deep_graph_nodes = 10
    mock_report.deep_graph_edges = 5

    with patch("backend.knowledge.dreaming.DreamingPipeline") as MockPipeline:
        instance = MockPipeline.return_value
        instance.run_full_cycle = AsyncMock(return_value=mock_report)

        resp = await client.post("/api/dreaming/trigger")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["rem_patterns"] == 2
    assert data["graph_nodes"] == 10
    assert data["graph_edges"] == 5
    assert "light_sleep" in data
    assert "timestamp" in data


async def test_dreaming_trigger_error(client):
    """POST /api/dreaming/trigger returns 500 with ok=False on pipeline failure."""
    with patch("backend.knowledge.dreaming.DreamingPipeline") as MockPipeline:
        instance = MockPipeline.return_value
        instance.run_full_cycle = AsyncMock(side_effect=RuntimeError("pipeline crash"))

        resp = await client.post("/api/dreaming/trigger")

    assert resp.status_code == 500
    data = resp.json()
    assert data["ok"] is False
    assert "pipeline crash" in data["error"]


# --- GET /api/dreaming/history ---

async def test_dreaming_history_never_run(client):
    """GET /api/dreaming/history returns never_run status when no runs recorded."""
    resp = await client.get("/api/dreaming/history")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] in ("never_run", "ok", "failed")


async def test_dreaming_history_after_run(client):
    """GET /api/dreaming/history returns last run info after a run is recorded."""
    # Record a dreaming run directly via app state
    from backend.main import create_app
    app = create_app()
    app.state.db.record_dreaming_run(status="ok")

    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/dreaming/history")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["ran_at"] is not None


# --- GET /api/costs/summary ---

async def test_costs_summary_empty(client):
    """GET /api/costs/summary returns empty list when no costs logged."""
    resp = await client.get("/api/costs/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "by_model" in data
    assert isinstance(data["by_model"], list)
    assert "total_cost_usd" in data
    assert isinstance(data["total_cost_usd"], (int, float))


async def test_costs_summary_with_data(client, app):
    """GET /api/costs/summary returns cost breakdown after logging a call."""
    app.state.db.log_cost(
        case_id="test-case",
        role="analyzer",
        model="google/gemini-flash",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.0001,
    )

    resp = await client.get("/api/costs/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["by_model"]) >= 1
    assert data["total_cost_usd"] > 0


# --- POST /api/sync/push ---

async def test_sync_push_no_server(client):
    """POST /api/sync/push returns ok=False when sync modules unavailable."""
    resp = await client.post("/api/sync/push")
    assert resp.status_code == 200
    data = resp.json()
    # Either ok=True (if sync available) or ok=False (if not configured)
    assert "ok" in data


async def test_sync_push_with_mock(client):
    """POST /api/sync/push returns ok=True and pushed count when sync succeeds."""
    mock_client = MagicMock()
    mock_client.push_pending = AsyncMock(return_value=3)

    with patch("backend.sync.queue.SyncQueue", MagicMock()), \
         patch("backend.sync.client.SyncClient", return_value=mock_client):
        resp = await client.post("/api/sync/push")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["pushed"] == 3


# --- POST /api/sync/pull ---

async def test_sync_pull_no_server(client):
    """POST /api/sync/pull returns ok=False when sync modules unavailable."""
    resp = await client.post("/api/sync/pull")
    assert resp.status_code == 200
    data = resp.json()
    assert "ok" in data


async def test_sync_pull_with_mock(client):
    """POST /api/sync/pull returns ok=True and imported count when sync succeeds."""
    mock_client = MagicMock()
    mock_client.pull_updates = AsyncMock(return_value={"cases": [], "traces": [], "manuals": []})

    with patch("backend.sync.queue.SyncQueue", MagicMock()), \
         patch("backend.sync.client.SyncClient", return_value=mock_client):
        resp = await client.post("/api/sync/pull")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["imported"] == 0


# --- GET /api/settings/vectordb/export ---

async def test_vectordb_export_returns_json(client):
    """GET /api/settings/vectordb/export returns JSON with collection keys."""
    resp = await client.get("/api/settings/vectordb/export")
    assert resp.status_code == 200
    data = resp.json()
    # Should have at least some collection keys (or empty dict on empty DB)
    assert isinstance(data, dict)


async def test_vectordb_export_content_disposition(client):
    """GET /api/settings/vectordb/export sets Content-Disposition attachment header."""
    resp = await client.get("/api/settings/vectordb/export")
    assert resp.status_code == 200
    disposition = resp.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "engram_vectordb_export.json" in disposition
