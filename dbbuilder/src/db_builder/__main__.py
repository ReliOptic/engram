"""CLI entry point for DB Builder.

Usage:
    python -m db_builder              # Launch GUI (default)
    python -m db_builder --cli build  # CLI mode
    python -m db_builder --cli status
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from db_builder.config import load_config
from db_builder.database import DatabaseManager
from db_builder.pipeline import FileScanner


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_status(config) -> None:
    """Show current DB Builder status."""
    db = DatabaseManager(config.db_path)
    db.init_schema()

    files = db.list_files()
    stats = db.get_build_stats()

    print(f"DB Builder Status")
    print(f"{'='*40}")
    print(f"Database: {config.db_path}")
    print(f"ChromaDB: {config.chromadb_dir}")
    print(f"Raw data: {config.raw_data_dir}")
    print()
    print(f"Files: {len(files)}")
    for status in ["pending", "parsing", "parsed", "chunked", "embedded", "completed", "failed"]:
        count = len([f for f in files if f["status"] == status])
        if count > 0:
            print(f"  {status}: {count}")
    print()
    print(f"Chunks: {stats.get('total_chunks', 0)}")
    print(f"  Accepted: {stats.get('accepted', 0)}")
    print(f"  Quarantined: {stats.get('quarantined', 0)}")
    print(f"  Embedded: {stats.get('embedded', 0)}")
    if stats.get("avg_quality"):
        print(f"  Avg Quality: {stats['avg_quality']:.3f}")

    db.close()


def cmd_scan(config) -> None:
    """Scan raw data directory for new/changed files."""
    db = DatabaseManager(config.db_path)
    db.init_schema()
    config.raw_data_dir.mkdir(parents=True, exist_ok=True)

    scanner = FileScanner(config.raw_data_dir, db)
    results = scanner.scan()

    print(f"Scan complete. {len(results)} new/changed file(s) found.")
    for r in results:
        print(f"  [{r['source_type']}] {r['file_path']}")

    db.close()


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="db-builder",
        description="ZEMAS DB Builder — Knowledge Base Construction Pipeline",
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="Run in CLI mode (no GUI)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show current status")
    sub.add_parser("scan", help="Scan raw data directory")

    build_p = sub.add_parser("build", help="Run build pipeline")
    build_group = build_p.add_mutually_exclusive_group()
    build_group.add_argument("--all", action="store_true", help="Build all pending files")
    build_group.add_argument("--source", type=str, help="Build by source type")
    build_group.add_argument("--file", type=str, help="Build single file")

    sub.add_parser("report", help="Show quality report")
    sub.add_parser("inspect", help="Launch Inspector UI")

    export_p = sub.add_parser("export", help="Export ChromaDB to ZEMAS")
    export_p.add_argument("--output", type=str, required=True, help="Output directory")

    rebuild_p = sub.add_parser("rebuild", help="Rebuild all (drop + re-create)")
    rebuild_p.add_argument("--confirm", action="store_true", required=True)

    return parser


def main() -> None:
    parser = build_cli_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.cli or args.command:
        # CLI mode
        config = load_config()

        if args.command == "status":
            cmd_status(config)
        elif args.command == "scan":
            cmd_scan(config)
        elif args.command == "build":
            print("Build pipeline not yet implemented (Phase 4)")
        elif args.command == "report":
            print("Quality report not yet implemented (Phase 5)")
        elif args.command == "inspect":
            print("Inspector UI not yet implemented (Phase 5)")
        elif args.command == "export":
            print("Export not yet implemented (Phase 4)")
        elif args.command == "rebuild":
            print("Rebuild not yet implemented (Phase 4)")
        else:
            parser.print_help()
    else:
        # GUI mode (default)
        config = load_config()
        from db_builder.app import run_gui
        sys.exit(run_gui(config=config))


if __name__ == "__main__":
    main()
