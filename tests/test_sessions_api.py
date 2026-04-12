"""Tests for session CRUD API and message persistence."""

import json
import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app


async def test_create_session(client):
    resp = await client.post("/api/sessions", json={"title": "Test Session"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Session"
    assert data["status"] == "active"
    assert "session_id" in data


async def test_list_sessions(client):
    # Create 2 sessions
    await client.post("/api/sessions", json={"title": "Session 1"})
    await client.post("/api/sessions", json={"title": "Session 2"})

    resp = await client.get("/api/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 2
    # Newest first
    assert sessions[0]["title"] == "Session 2"


async def test_get_session_with_messages(client):
    # Create session
    resp = await client.post("/api/sessions", json={"title": "Chat 1"})
    sid = resp.json()["session_id"]

    # Get session (with messages)
    resp = await client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Chat 1"
    assert data["messages"] == []


async def test_get_session_not_found(client):
    resp = await client.get("/api/sessions/nonexistent")
    assert resp.status_code == 404


async def test_update_session_title(client):
    resp = await client.post("/api/sessions", json={"title": "Old Title"})
    sid = resp.json()["session_id"]

    resp = await client.patch(f"/api/sessions/{sid}", json={"title": "New Title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New Title"


async def test_archive_session(client):
    resp = await client.post("/api/sessions", json={"title": "To Archive"})
    sid = resp.json()["session_id"]

    resp = await client.patch(f"/api/sessions/{sid}", json={"status": "archived"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


async def test_delete_session(client):
    resp = await client.post("/api/sessions", json={"title": "To Delete"})
    sid = resp.json()["session_id"]

    resp = await client.delete(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify deleted
    resp = await client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 404


async def test_message_persistence_via_db(tmp_path):
    """Test that messages are persisted correctly through the DB layer."""
    from backend.knowledge.database import EngramDB

    db_path = tmp_path / "test_sessions.db"
    db = EngramDB(str(db_path))
    try:
        sid = db.create_session(title="DB Test")
        db.add_message(session_id=sid, agent="user", content="Hello")
        db.add_message(session_id=sid, agent="analyzer", content="Analysis", contribution_type="NEW_EVIDENCE")

        messages = db.get_messages(sid)
        assert len(messages) == 2
        assert messages[0]["agent"] == "user"
        assert messages[1]["agent"] == "analyzer"
        assert messages[1]["contribution_type"] == "NEW_EVIDENCE"

        # Session message_count updated
        session = db.get_session(sid)
        assert session["message_count"] == 2
    finally:
        db.close()


async def test_session_list_filter_status(client):
    await client.post("/api/sessions", json={"title": "Active 1"})
    resp2 = await client.post("/api/sessions", json={"title": "To Archive"})
    sid = resp2.json()["session_id"]
    await client.patch(f"/api/sessions/{sid}", json={"status": "archived"})

    # Only active
    resp = await client.get("/api/sessions?status=active")
    sessions = resp.json()
    assert len(sessions) == 1
    assert sessions[0]["title"] == "Active 1"
