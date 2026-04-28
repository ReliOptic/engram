"""Tests for GET /api/chunks/{chunk_id} endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client_with_chunks(app):
    """App client with pre-seeded chunks in each collection."""
    from backend.knowledge.vectordb import VectorDB
    import backend.config as _cfg

    vdb = VectorDB(persist_dir=str(_cfg.DATA_DIR / "chroma_db"))
    vdb.add("case_records", {
        "id": "chunk-case-001",
        "document": "Case record document text",
        "metadata": {"account": "ClientA", "tool": "ProductA", "silo_key": "ClientA_ProductA_M1"},
    })
    vdb.add("manuals", {
        "id": "chunk-manual-001",
        "document": "Manual section text",
        "metadata": {"tool_family": "ProductA", "section": "Installation"},
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_chunk_returns_document(client_with_chunks):
    resp = await client_with_chunks.get("/api/chunks/chunk-case-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "chunk-case-001"
    assert data["document"] == "Case record document text"
    assert data["collection"] == "case_records"
    assert isinstance(data["metadata"], dict)


@pytest.mark.asyncio
async def test_get_chunk_finds_in_manuals(client_with_chunks):
    resp = await client_with_chunks.get("/api/chunks/chunk-manual-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "chunk-manual-001"
    assert data["collection"] == "manuals"


@pytest.mark.asyncio
async def test_get_chunk_not_found_returns_404(client_with_chunks):
    resp = await client_with_chunks.get("/api/chunks/nonexistent-id-xyz")
    assert resp.status_code == 404
    assert "detail" in resp.json()
