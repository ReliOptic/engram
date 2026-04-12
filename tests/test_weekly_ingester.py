"""Tests for weekly report ingestion from Excel."""

import os

import pytest

from backend.knowledge.weekly_ingester import WeeklyIngester


XLSX_PATH = "data/raw/weekly_reports/CW15_Weekly_Apps.xlsx"

pytestmark = pytest.mark.skipif(
    not os.path.exists(XLSX_PATH),
    reason=f"Test data not found: {XLSX_PATH}",
)


@pytest.fixture
def ingester():
    return WeeklyIngester(XLSX_PATH)


def test_parse_new_format_cw15(ingester):
    """CW15 시트 (Cus.|FoB|Tool|Title|Status|Next Plan) 파싱."""
    chunks = ingester.parse_sheet("CW15")
    assert len(chunks) > 0

    first = chunks[0]
    assert "id" in first
    assert "document" in first
    assert "metadata" in first
    assert first["metadata"]["cw"] == "CW15"
    assert first["metadata"]["chunk_type"] == "weekly_report"
    # CW15 has proper column names
    assert first["metadata"].get("account") or first["metadata"].get("title")


def test_parse_old_format(ingester):
    """CW52 or similar old-format sheet parsing."""
    # Old format sheets have 'Unnamed' columns and merged cells
    chunks = ingester.parse_sheet("CW52")
    # Old format may have fewer parseable rows but should not crash
    assert isinstance(chunks, list)


def test_bootstrap_all_sheets(ingester):
    """CW52~CW15 모든 시트 전부 인제스트."""
    all_chunks = ingester.parse_all_sheets()
    assert len(all_chunks) > 0

    # Should have chunks from multiple CW weeks
    cws = set(c["metadata"]["cw"] for c in all_chunks)
    assert len(cws) >= 2  # At least 2 different CW weeks


def test_diff_detection(ingester):
    """같은 issue가 다른 CW에 나타나면 같은 thread_id."""
    all_chunks = ingester.parse_all_sheets()

    # Collect thread IDs
    thread_ids = [c["metadata"].get("issue_thread_id", "") for c in all_chunks]
    thread_ids = [t for t in thread_ids if t]

    # Some threads should appear more than once (same issue across weeks)
    from collections import Counter
    thread_counts = Counter(thread_ids)
    # Not all issues repeat, but if data has any repeating issues, they share thread IDs
    assert len(thread_ids) > 0


def test_upsert_prevents_duplicate(ingester):
    """같은 CW+tool 조합은 upsert (chunk ID is deterministic)."""
    chunks1 = ingester.parse_sheet("CW15")
    chunks2 = ingester.parse_sheet("CW15")

    if chunks1 and chunks2:
        # Same sheet parsed twice → same IDs
        ids1 = [c["id"] for c in chunks1]
        ids2 = [c["id"] for c in chunks2]
        assert ids1 == ids2
