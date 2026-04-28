"""Tests for AutoIngester — directory watching, manifest, VectorDB ingestion."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.knowledge.auto_ingester import AutoIngester


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_xlsx(path: Path) -> None:
    """Create a minimal valid xlsx with new-format columns."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CW20"
    ws.append(["Cus.", "FoB", "Tool", "Title", "Status", "Next Plan"])
    ws.append(["ClientA", "FSE", "ProductA", "PRV offset after PM", "Closed", "Monitor"])
    wb.save(str(path))


def _make_mock_vdb() -> MagicMock:
    vdb = MagicMock()
    vdb.upsert_batch.return_value = ["chunk-id-1"]
    return vdb


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_returns_empty_when_directory_missing(tmp_path: Path) -> None:
    """Missing watch directory → scan_and_ingest returns empty list."""
    vdb = _make_mock_vdb()
    auto = AutoIngester(tmp_path / "nonexistent", vdb)

    result = await auto.scan_and_ingest()

    assert result == []
    vdb.upsert_batch.assert_not_called()


@pytest.mark.asyncio
async def test_scan_finds_xlsx_files_and_ingests(tmp_path: Path) -> None:
    """A new xlsx file in watch_dir is ingested exactly once."""
    watch_dir = tmp_path / "weekly_reports"
    watch_dir.mkdir()
    _make_xlsx(watch_dir / "CW20_report.xlsx")

    vdb = _make_mock_vdb()
    auto = AutoIngester(watch_dir, vdb)

    result = await auto.scan_and_ingest()

    assert result == ["CW20_report.xlsx"]
    vdb.upsert_batch.assert_called_once()
    # First arg is collection name, second is chunks list
    call_args = vdb.upsert_batch.call_args
    assert call_args[0][0] == "weekly"
    chunks = call_args[0][1]
    assert isinstance(chunks, list)
    assert len(chunks) >= 1


@pytest.mark.asyncio
async def test_already_processed_files_are_skipped(tmp_path: Path) -> None:
    """Files listed in .processed.json manifest are not re-ingested."""
    watch_dir = tmp_path / "weekly_reports"
    watch_dir.mkdir()
    _make_xlsx(watch_dir / "CW20_report.xlsx")

    manifest = watch_dir / ".processed.json"
    manifest.write_text(json.dumps({"processed": ["CW20_report.xlsx"]}))

    vdb = _make_mock_vdb()
    auto = AutoIngester(watch_dir, vdb)

    result = await auto.scan_and_ingest()

    assert result == []
    vdb.upsert_batch.assert_not_called()


@pytest.mark.asyncio
async def test_manifest_updated_after_ingestion(tmp_path: Path) -> None:
    """After successful ingestion, filename appears in .processed.json."""
    watch_dir = tmp_path / "weekly_reports"
    watch_dir.mkdir()
    _make_xlsx(watch_dir / "CW20_report.xlsx")

    vdb = _make_mock_vdb()
    auto = AutoIngester(watch_dir, vdb)

    await auto.scan_and_ingest()

    manifest = watch_dir / ".processed.json"
    assert manifest.exists()
    data = json.loads(manifest.read_text())
    assert "CW20_report.xlsx" in data["processed"]


@pytest.mark.asyncio
async def test_failed_ingestion_does_not_update_manifest(tmp_path: Path) -> None:
    """If WeeklyIngester raises, the file is NOT added to the manifest."""
    watch_dir = tmp_path / "weekly_reports"
    watch_dir.mkdir()
    _make_xlsx(watch_dir / "CW20_report.xlsx")

    vdb = _make_mock_vdb()
    auto = AutoIngester(watch_dir, vdb)

    with patch(
        "backend.knowledge.auto_ingester.WeeklyIngester",
        side_effect=RuntimeError("parse failed"),
    ):
        result = await auto.scan_and_ingest()

    assert result == []
    manifest = watch_dir / ".processed.json"
    assert not manifest.exists()


@pytest.mark.asyncio
async def test_scan_and_ingest_is_idempotent(tmp_path: Path) -> None:
    """Calling scan_and_ingest twice only ingests the file the first time."""
    watch_dir = tmp_path / "weekly_reports"
    watch_dir.mkdir()
    _make_xlsx(watch_dir / "CW20_report.xlsx")

    vdb = _make_mock_vdb()
    auto = AutoIngester(watch_dir, vdb)

    first = await auto.scan_and_ingest()
    second = await auto.scan_and_ingest()

    assert first == ["CW20_report.xlsx"]
    assert second == []
    # upsert_batch called exactly once across both runs
    assert vdb.upsert_batch.call_count == 1
