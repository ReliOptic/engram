"""Auto-ingester — watches data/weekly_reports/ for new Excel files.

Runs as a background asyncio task started at server startup.
Polls every POLL_INTERVAL seconds for new xlsx files.
Tracks processed files in .processed.json manifest to avoid re-ingestion.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from backend.knowledge.weekly_ingester import WeeklyIngester

logger = logging.getLogger(__name__)

POLL_INTERVAL = 30  # seconds between scans


class AutoIngester:
    def __init__(self, watch_dir: Path, vectordb) -> None:
        self._watch_dir = Path(watch_dir)
        self._manifest_path = self._watch_dir / ".processed.json"
        self._vdb = vectordb

    def _load_manifest(self) -> set[str]:
        if self._manifest_path.exists():
            try:
                data = json.loads(self._manifest_path.read_text())
                return set(data.get("processed", []))
            except Exception:
                return set()
        return set()

    def _save_manifest(self, processed: set[str]) -> None:
        self._manifest_path.write_text(
            json.dumps({"processed": sorted(processed)}, indent=2)
        )

    async def scan_and_ingest(self) -> list[str]:
        """Scan watch_dir for new xlsx files and ingest them.

        Returns list of filenames that were successfully ingested.
        """
        if not self._watch_dir.exists():
            return []

        processed = self._load_manifest()
        ingested: list[str] = []

        for xlsx_path in sorted(self._watch_dir.glob("*.xlsx")):
            file_key = xlsx_path.name
            if file_key in processed:
                continue

            try:
                ingester = WeeklyIngester(str(xlsx_path))
                chunks = await asyncio.to_thread(ingester.parse_all_sheets)
                self._vdb.upsert_batch("weekly", chunks)
                processed.add(file_key)
                ingested.append(file_key)
                logger.info(
                    "auto-ingested: %s (%d chunks)", file_key, len(chunks)
                )
            except Exception as exc:
                logger.error("auto-ingest failed for %s: %s", file_key, exc)

        if ingested:
            self._save_manifest(processed)

        return ingested

    async def run_watcher(self, interval: int = POLL_INTERVAL) -> None:
        """Background loop — poll forever, ingest new files."""
        while True:
            await asyncio.sleep(interval)
            try:
                await self.scan_and_ingest()
            except Exception as exc:
                logger.error("auto-ingester loop error: %s", exc)
