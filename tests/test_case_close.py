"""Tests for POST /api/sessions/{session_id}/close endpoint.

TDD: these tests are written before the implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_case_recorder():
    """Mock CaseRecorder that returns deterministic chunk IDs."""
    recorder = MagicMock()
    recorder.record_case = AsyncMock(return_value=("type-a-id-001", "type-b-id-001"))
    return recorder


@pytest.fixture
def app_with_recorder(app, mock_case_recorder):
    """Inject mock CaseRecorder into app.state."""
    app.state.case_recorder = mock_case_recorder
    return app


@pytest.fixture
async def client_with_recorder(app_with_recorder):
    transport = ASGITransport(app=app_with_recorder)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_close_records_case_to_vectordb(client_with_recorder, app_with_recorder):
    """POST /api/sessions/{id}/close calls CaseRecorder.record_case() exactly once."""
    # Create a session with silo info
    resp = await client_with_recorder.post(
        "/api/sessions",
        json={
            "title": "Test close session",
            "silo_account": "ClientA",
            "silo_tool": "ProductA",
            "silo_component": "Module1",
        },
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    resp = await client_with_recorder.post(
        f"/api/sessions/{session_id}/close",
        json={"resolution": "Fixed by resetting module"},
    )
    assert resp.status_code == 200

    recorder = app_with_recorder.state.case_recorder
    recorder.record_case.assert_called_once()


async def test_close_returns_chunk_ids(client_with_recorder):
    """Close response contains status, type_a_id, type_b_id, tacit_count."""
    resp = await client_with_recorder.post(
        "/api/sessions",
        json={"title": "Chunk ID test"},
    )
    session_id = resp.json()["session_id"]

    resp = await client_with_recorder.post(
        f"/api/sessions/{session_id}/close",
        json={"resolution": "Issue resolved"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "closed"
    assert data["type_a_id"] == "type-a-id-001"
    assert data["type_b_id"] == "type-b-id-001"
    assert "tacit_count" in data
    assert isinstance(data["tacit_count"], int)


async def test_close_already_closed_returns_409(client_with_recorder):
    """Calling close twice on the same session returns 409."""
    resp = await client_with_recorder.post(
        "/api/sessions",
        json={"title": "Double close test"},
    )
    session_id = resp.json()["session_id"]

    # First close succeeds
    resp = await client_with_recorder.post(
        f"/api/sessions/{session_id}/close",
        json={"resolution": "Done"},
    )
    assert resp.status_code == 200

    # Second close returns 409
    resp = await client_with_recorder.post(
        f"/api/sessions/{session_id}/close",
        json={"resolution": "Done again"},
    )
    assert resp.status_code == 409


async def test_close_nonexistent_session_returns_404(client_with_recorder):
    """Closing a nonexistent session returns 404."""
    resp = await client_with_recorder.post(
        "/api/sessions/nonexistent-id/close",
        json={"resolution": "N/A"},
    )
    assert resp.status_code == 404


async def test_close_marks_session_closed_in_db(client_with_recorder, app_with_recorder):
    """After close, session status is 'closed' in the DB."""
    resp = await client_with_recorder.post(
        "/api/sessions",
        json={"title": "Status check"},
    )
    session_id = resp.json()["session_id"]

    await client_with_recorder.post(
        f"/api/sessions/{session_id}/close",
        json={"resolution": "Resolved"},
    )

    session = app_with_recorder.state.db.get_session(session_id)
    assert session["status"] == "closed"
