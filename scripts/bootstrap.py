"""Bootstrap script — bulk ingest existing data into VectorDB.

Usage:
    python scripts/bootstrap.py --weekly data/raw/weekly_reports/CW15_Weekly_Apps.xlsx
    python scripts/bootstrap.py --all

Spec reference: scaffolding-plan-v3.md Section 5.5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.knowledge.vectordb import VectorDB
from backend.knowledge.weekly_ingester import WeeklyIngester


def bootstrap_weekly(xlsx_path: str, vectordb: VectorDB) -> int:
    """Ingest all sheets from a weekly report Excel file.

    Returns number of chunks ingested.
    """
    ingester = WeeklyIngester(xlsx_path)
    all_chunks = ingester.parse_all_sheets()

    if all_chunks:
        vectordb.upsert_batch("weekly", all_chunks)

    print(f"Ingested {len(all_chunks)} weekly report chunks from {len(ingester.sheet_names)} sheets")
    return len(all_chunks)


def main():
    parser = argparse.ArgumentParser(description="Engram Bootstrap — bulk data ingest")
    parser.add_argument("--weekly", type=str, help="Path to weekly report Excel file")
    parser.add_argument("--all", action="store_true", help="Ingest all available data")
    parser.add_argument("--persist-dir", type=str, default="data/chroma_db",
                        help="ChromaDB persist directory")
    args = parser.parse_args()

    vectordb = VectorDB(persist_dir=args.persist_dir)

    total = 0

    if args.weekly or args.all:
        xlsx = args.weekly or "data/raw/weekly_reports/CW15_Weekly_Apps.xlsx"
        total += bootstrap_weekly(xlsx, vectordb)

    if total == 0 and not args.all:
        parser.print_help()
    else:
        print(f"\nTotal: {total} chunks ingested")


if __name__ == "__main__":
    main()
