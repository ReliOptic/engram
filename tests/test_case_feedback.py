"""Tests for case feedback loop — POST/GET /api/sessions/{id}/feedback."""

import pytest


@pytest.mark.asyncio
async def test_submit_feedback_stores_to_db(client, app):
    """POST /api/sessions/{id}/feedback {"helpful": true} → 200."""
    db = app.state.db
    session_id = db.create_session(title="test session")

    resp = await client.post(
        f"/api/sessions/{session_id}/feedback",
        json={"helpful": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["helpful"] is True
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_get_feedback_returns_submitted_value(client, app):
    """GET /api/sessions/{id}/feedback → {"helpful": true, "timestamp": str}."""
    db = app.state.db
    session_id = db.create_session(title="test session")

    await client.post(
        f"/api/sessions/{session_id}/feedback",
        json={"helpful": False},
    )

    resp = await client.get(f"/api/sessions/{session_id}/feedback")
    assert resp.status_code == 200
    body = resp.json()
    assert body["helpful"] is False
    assert isinstance(body["timestamp"], str)
    assert body["timestamp"]


@pytest.mark.asyncio
async def test_duplicate_feedback_returns_409(client, app):
    """Submitting feedback twice for the same session → 409."""
    db = app.state.db
    session_id = db.create_session(title="test session")

    await client.post(
        f"/api/sessions/{session_id}/feedback",
        json={"helpful": True},
    )
    resp = await client.post(
        f"/api/sessions/{session_id}/feedback",
        json={"helpful": False},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_feedback_not_found_returns_404(client, app):
    """GET feedback before submitting → 404."""
    db = app.state.db
    session_id = db.create_session(title="test session")

    resp = await client.get(f"/api/sessions/{session_id}/feedback")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_feedback_on_unknown_session_returns_404(client):
    """POST feedback for a non-existent session → 404."""
    resp = await client.post(
        "/api/sessions/no-such-session/feedback",
        json={"helpful": True},
    )
    assert resp.status_code == 404
