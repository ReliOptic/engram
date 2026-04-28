"""Tests for /api/upload OCR, WebSocket attachment injection, and /api/knowledge/ingest.

These tests cover the three behaviors added in the cold-start / speed strategy:

1. Image uploads trigger OCR and return extracted_text in the response.
2. Non-image uploads return extracted_text: null without calling OCR.
3. WebSocket user_message with attachment.extracted_text appends it to the query.
4. POST /api/knowledge/ingest triggers a scan and returns the result.
"""

import io
import json
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# /api/upload — OCR behaviour
# ---------------------------------------------------------------------------

async def test_upload_non_image_returns_null_extracted_text(client):
    """CSV/text uploads skip OCR; extracted_text is null in response."""
    resp = await client.post(
        "/api/upload",
        files={"file": ("report.csv", io.BytesIO(b"col1,col2\nval1,val2"), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "report.csv"
    assert data["extracted_text"] is None


async def test_upload_image_calls_ocr_returns_extracted_text(client):
    """PNG upload triggers OCR; extracted_text reflects the OCR result."""
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    with patch("backend.main._ocr_image", new=AsyncMock(return_value="ERROR CODE E-450")):
        resp = await client.post(
            "/api/upload",
            files={"file": ("error_screen.png", io.BytesIO(fake_png), "image/png")},
        )
    assert resp.status_code == 200
    assert resp.json()["extracted_text"] == "ERROR CODE E-450"


async def test_upload_image_empty_ocr_result_returns_null(client):
    """Empty OCR result (API key missing, API error) is returned as null, not ''."""
    fake_jpg = b"\xff\xd8\xff" + b"\x00" * 50
    with patch("backend.main._ocr_image", new=AsyncMock(return_value="")):
        resp = await client.post(
            "/api/upload",
            files={"file": ("photo.jpg", io.BytesIO(fake_jpg), "image/jpeg")},
        )
    assert resp.status_code == 200
    assert resp.json()["extracted_text"] is None


async def test_upload_response_includes_filename_and_size(client):
    """Response always includes filename and size_bytes regardless of file type."""
    content = b"hello"
    resp = await client.post(
        "/api/upload",
        files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "test.txt"
    assert data["size_bytes"] == len(content)
    assert "saved_as" in data


# ---------------------------------------------------------------------------
# WebSocket — attachment.extracted_text injected into query
# ---------------------------------------------------------------------------

def test_websocket_attachment_text_appended_to_query(app):
    """extracted_text from attachments is appended to the user query before orchestration."""
    captured: list[str] = []

    async def mock_orchestrator(app, websocket, query, silo, session_id=""):
        captured.append(query)

    with patch("backend.main._run_orchestrator", new=mock_orchestrator):
        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                ws.send_text(json.dumps({
                    "type": "user_message",
                    "payload": {
                        "text": "PRV pressure drop",
                        "silo": {"account": "ClientA", "tool": "ProductA"},
                        "attachments": [
                            {
                                "filename": "error.png",
                                "saved_as": "/tmp/error.png",
                                "size_bytes": 1024,
                                "extracted_text": "ERROR CODE E-450",
                            }
                        ],
                    },
                }))
                ws.receive_text()  # consume status_update

    assert len(captured) == 1
    assert "PRV pressure drop" in captured[0]
    assert "ERROR CODE E-450" in captured[0]
    assert "[Attached image text:" in captured[0]


def test_websocket_attachment_without_extracted_text_is_ignored(app):
    """Attachment with no extracted_text does not modify the query text."""
    captured: list[str] = []

    async def mock_orchestrator(app, websocket, query, silo, session_id=""):
        captured.append(query)

    with patch("backend.main._run_orchestrator", new=mock_orchestrator):
        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                ws.send_text(json.dumps({
                    "type": "user_message",
                    "payload": {
                        "text": "valve issue",
                        "silo": {},
                        "attachments": [
                            {"filename": "doc.pdf", "saved_as": "/tmp/doc.pdf", "size_bytes": 512},
                        ],
                    },
                }))
                ws.receive_text()

    assert len(captured) == 1
    assert captured[0] == "valve issue"


def test_websocket_multiple_attachments_all_appended(app):
    """Multiple attachments with extracted_text are all appended to the query."""
    captured: list[str] = []

    async def mock_orchestrator(app, websocket, query, silo, session_id=""):
        captured.append(query)

    with patch("backend.main._run_orchestrator", new=mock_orchestrator):
        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                ws.send_text(json.dumps({
                    "type": "user_message",
                    "payload": {
                        "text": "check both",
                        "silo": {},
                        "attachments": [
                            {"filename": "a.png", "extracted_text": "TEXT_A"},
                            {"filename": "b.png", "extracted_text": "TEXT_B"},
                        ],
                    },
                }))
                ws.receive_text()

    assert "TEXT_A" in captured[0]
    assert "TEXT_B" in captured[0]


# ---------------------------------------------------------------------------
# POST /api/knowledge/ingest — manual trigger
# ---------------------------------------------------------------------------

async def test_knowledge_ingest_returns_empty_for_empty_watch_dir(client):
    """Empty weekly_reports/ dir returns ingested=[], count=0."""
    resp = await client.post("/api/knowledge/ingest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ingested"] == []
    assert data["count"] == 0


async def test_knowledge_ingest_response_has_required_keys(client):
    """Response always includes 'ingested' list and 'count' integer."""
    resp = await client.post("/api/knowledge/ingest")
    assert resp.status_code == 200
    data = resp.json()
    assert "ingested" in data
    assert "count" in data
    assert isinstance(data["ingested"], list)
    assert isinstance(data["count"], int)
