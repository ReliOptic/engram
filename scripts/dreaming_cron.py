"""Nightly dreaming job — run as cron/scheduled task.

Usage:
    python scripts/dreaming_cron.py
    python scripts/dreaming_cron.py --export-graph data/graph.json

For Windows Task Scheduler, create a task that runs:
    python /path/to/scripts/dreaming_cron.py

Spec reference: scaffolding-plan-v3.md Section 5.3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio

from backend.knowledge.vectordb import VectorDB
from backend.knowledge.dreaming import DreamingPipeline


async def run_dreaming(persist_dir: str, export_graph: str | None):
    vectordb = VectorDB(persist_dir=persist_dir)
    pipeline = DreamingPipeline(vectordb)

    print("Starting dreaming cycle...")
    report = await pipeline.run_full_cycle()

    print(f"\n=== Dreaming Report ({report.timestamp}) ===")

    for dedup in report.light_sleep:
        print(f"  [{dedup.collection}] items={dedup.total_items}, "
              f"near_dupes={dedup.near_duplicates_found}, "
              f"merged={dedup.merged_count}, "
              f"traces_skipped={dedup.skipped_traces}")

    print(f"  REM patterns: {len(report.rem_patterns)}")
    for p in report.rem_patterns:
        flag = " ** PROMOTION CANDIDATE **" if p["promotion_candidate"] else ""
        print(f"    {p['type']}: {p['count']} occurrences{flag}")

    print(f"  Graph: {report.deep_graph_nodes} nodes, {report.deep_graph_edges} edges")

    if export_graph:
        graph_data = pipeline.export_graph()
        Path(export_graph).write_text(json.dumps(graph_data, indent=2))
        print(f"\n  Graph exported to {export_graph}")


def main():
    parser = argparse.ArgumentParser(description="Engram Dreaming — nightly consolidation")
    parser.add_argument("--persist-dir", default="data/chroma_db", help="ChromaDB directory")
    parser.add_argument("--export-graph", type=str, help="Export graph to JSON file")
    args = parser.parse_args()

    asyncio.run(run_dreaming(args.persist_dir, args.export_graph))


if __name__ == "__main__":
    main()
