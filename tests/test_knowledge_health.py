"""Tests for GET /api/knowledge/health endpoint."""

import pytest


async def test_health_returns_required_fields(client):
    """Health endpoint returns all required fields."""
    resp = await client.get("/api/knowledge/health")
    assert resp.status_code == 200
    data = resp.json()

    assert "total_cases" in data
    assert "total_chunks" in data
    assert "last_dreaming_run" in data
    assert "dreaming_status" in data
    assert "weekly_files_processed" in data
    assert "feedback_positive_rate" in data


async def test_health_dreaming_status_never_run_when_no_log(client):
    """Fresh DB with no dreaming_log table → dreaming_status is 'never_run'."""
    resp = await client.get("/api/knowledge/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["dreaming_status"] == "never_run"
    assert data["last_dreaming_run"] is None


async def test_health_total_cases_zero_when_empty(client):
    """No cases in DB → total_cases is 0."""
    resp = await client.get("/api/knowledge/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_cases"] == 0


async def test_health_total_chunks_zero_when_empty(client):
    """Empty ChromaDB → total_chunks is 0."""
    resp = await client.get("/api/knowledge/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_chunks"] == 0


async def test_health_weekly_files_processed_zero_when_empty(client):
    """No weekly files ingested → weekly_files_processed is 0."""
    resp = await client.get("/api/knowledge/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["weekly_files_processed"] == 0


async def test_health_feedback_positive_rate_null_when_no_feedback(client):
    """No feedback records → feedback_positive_rate is null."""
    resp = await client.get("/api/knowledge/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["feedback_positive_rate"] is None


async def test_health_total_cases_reflects_closed_cases(client):
    """total_cases counts closed cases in SQLite."""
    import backend.config as _cfg
    from backend.knowledge.database import EngramDB

    db_path = _cfg.DATA_DIR / "sqlite" / "engram.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = EngramDB(str(db_path))
    db.create_case(
        case_id="HEALTH-001",
        account="ClientA",
        tool="ProductA",
        component="Module1",
        title="Health test case",
    )
    db.close_case("HEALTH-001", "Resolved")
    db.close()

    resp = await client.get("/api/knowledge/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cases"] >= 1


async def test_health_dreaming_status_ok_when_log_exists(client):
    """dreaming_log with a successful run → dreaming_status is 'ok'."""
    import backend.config as _cfg
    from backend.knowledge.database import EngramDB

    db_path = _cfg.DATA_DIR / "sqlite" / "engram.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = EngramDB(str(db_path))
    db._conn.execute("DROP TABLE IF EXISTS dreaming_log")
    db._conn.execute("""
        CREATE TABLE dreaming_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ran_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            chunks_processed INTEGER NOT NULL DEFAULT 0,
            error_message TEXT DEFAULT NULL
        )
    """)
    db._conn.execute(
        "INSERT INTO dreaming_log (ran_at, status, chunks_processed) VALUES (?, ?, ?)",
        ("2026-04-28T00:00:00+00:00", "ok", 5),
    )
    db._conn.commit()
    db.close()

    resp = await client.get("/api/knowledge/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dreaming_status"] == "ok"
    assert data["last_dreaming_run"] == "2026-04-28T00:00:00+00:00"


async def test_health_dreaming_status_failed_when_last_run_failed(client):
    """dreaming_log with last run having status='failed' → dreaming_status is 'failed'."""
    import backend.config as _cfg
    from backend.knowledge.database import EngramDB

    db_path = _cfg.DATA_DIR / "sqlite" / "engram.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = EngramDB(str(db_path))
    db._conn.execute("DROP TABLE IF EXISTS dreaming_log")
    db._conn.execute("""
        CREATE TABLE dreaming_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ran_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            chunks_processed INTEGER NOT NULL DEFAULT 0,
            error_message TEXT DEFAULT NULL
        )
    """)
    db._conn.execute(
        "INSERT INTO dreaming_log (ran_at, status, chunks_processed) VALUES (?, ?, ?)",
        ("2026-04-27T00:00:00+00:00", "ok", 3),
    )
    db._conn.execute(
        "INSERT INTO dreaming_log (ran_at, status, chunks_processed) VALUES (?, ?, ?)",
        ("2026-04-28T00:00:00+00:00", "failed", 0),
    )
    db._conn.commit()
    db.close()

    resp = await client.get("/api/knowledge/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dreaming_status"] == "failed"
