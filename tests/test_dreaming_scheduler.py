"""Tests for dreaming scheduler — database logging and lifespan background task."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.knowledge.database import EngramDB


@pytest.fixture
def db(tmp_path: Path) -> EngramDB:
    return EngramDB(str(tmp_path / "test.db"))


def test_dreaming_log_table_exists(db: EngramDB) -> None:
    """dreaming_log table must exist after EngramDB init."""
    row = db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dreaming_log'"
    ).fetchone()
    assert row is not None, "dreaming_log table not found"


def test_record_dreaming_run_stores_timestamp(db: EngramDB) -> None:
    """record_dreaming_run stores a row and get_last_dreaming_run returns it."""
    db.record_dreaming_run("ok")
    result = db.get_last_dreaming_run()
    assert result is not None
    assert result["status"] == "ok"
    assert result["ran_at"]


def test_record_dreaming_run_with_error(db: EngramDB) -> None:
    """record_dreaming_run stores error_msg when provided."""
    db.record_dreaming_run("failed", "some error")
    result = db.get_last_dreaming_run()
    assert result is not None
    assert result["status"] == "failed"


def test_get_last_dreaming_run_returns_none_when_empty(db: EngramDB) -> None:
    """get_last_dreaming_run returns None when no runs recorded."""
    result = db.get_last_dreaming_run()
    assert result is None


def test_get_last_dreaming_run_returns_most_recent(db: EngramDB) -> None:
    """get_last_dreaming_run returns the most recent entry."""
    db.record_dreaming_run("ok")
    db.record_dreaming_run("failed", "oops")
    result = db.get_last_dreaming_run()
    assert result is not None
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_dreaming_failure_does_not_crash(tmp_path: Path) -> None:
    """Scheduler catches DreamingPipeline.run_full_cycle exceptions and logs them."""
    from backend.main import create_app
    from backend.knowledge.dreaming import DreamingPipeline

    db_path = str(tmp_path / "sqlite" / "engram.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = EngramDB(db_path)

    crash_called = False

    async def _fake_run_full_cycle():
        nonlocal crash_called
        crash_called = True
        raise RuntimeError("pipeline exploded")

    mock_pipeline = MagicMock(spec=DreamingPipeline)
    mock_pipeline.run_full_cycle = _fake_run_full_cycle

    from backend.main import _dreaming_loop
    import backend.main as _main_mod

    app = MagicMock()
    app.state.db = db

    with patch("backend.knowledge.dreaming.DreamingPipeline", return_value=mock_pipeline):
        task = asyncio.create_task(_dreaming_loop(app, run_immediately=True))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert crash_called
    last = db.get_last_dreaming_run()
    assert last is not None
    assert last["status"] == "failed"
    assert "pipeline exploded" in last["error_msg"]
