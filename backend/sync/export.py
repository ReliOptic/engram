"""Knowledge export/import — share ZEMAS data via ZIP file.

For giving colleagues a copy of your knowledge base without setting
up a sync server. They unzip, run import, and have your cases +
manuals in their local ZEMAS.

Usage:
    python -m backend.sync.export --output zemas-pack.zip
    python -m backend.sync.import --input zemas-pack.zip
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

logger = logging.getLogger(__name__)


def export_knowledge(
    data_dir: Path,
    output_path: Path,
    include_manuals: bool = True,
    include_cases: bool = True,
) -> dict:
    """Export cases, sessions, and optionally manuals to a ZIP.

    Returns stats dict with counts.
    """
    stats = {"sessions": 0, "messages": 0, "manuals_chunks": 0}

    with ZipFile(output_path, "w") as zf:
        # Export sessions + messages from SQLite
        db_path = data_dir / "sqlite" / "zemas.db"
        if db_path.exists() and include_cases:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            sessions = conn.execute(
                "SELECT * FROM sessions WHERE status = 'active'"
            ).fetchall()
            sessions_data = [dict(s) for s in sessions]
            stats["sessions"] = len(sessions_data)
            zf.writestr("sessions.json", json.dumps(sessions_data, indent=2, default=str))

            messages = conn.execute("SELECT * FROM messages").fetchall()
            messages_data = [dict(m) for m in messages]
            stats["messages"] = len(messages_data)
            zf.writestr("messages.json", json.dumps(messages_data, indent=2, default=str))

            conn.close()

        # Export ChromaDB manuals directory
        chroma_dir = data_dir / "chroma_db"
        if chroma_dir.exists() and include_manuals:
            for f in chroma_dir.rglob("*"):
                if f.is_file():
                    arcname = f"chroma_db/{f.relative_to(chroma_dir)}"
                    zf.write(f, arcname)
                    stats["manuals_chunks"] += 1

        # Metadata
        meta = {
            "exported_at": datetime.now(tz=UTC).isoformat(),
            "stats": stats,
            "version": "1.0",
        }
        zf.writestr("meta.json", json.dumps(meta, indent=2))

    logger.info("Exported to %s: %s", output_path, stats)
    return stats


def import_knowledge(
    data_dir: Path,
    input_path: Path,
    merge_sessions: bool = True,
    merge_manuals: bool = True,
) -> dict:
    """Import knowledge from a ZIP file into the local ZEMAS.

    Sessions/messages are merged (skip duplicates by session_id).
    ChromaDB files are copied (overwrite if newer).
    """
    stats = {"sessions_added": 0, "messages_added": 0, "chroma_files": 0}

    with ZipFile(input_path, "r") as zf:
        # Import sessions
        if merge_sessions and "sessions.json" in zf.namelist():
            sessions = json.loads(zf.read("sessions.json"))
            messages = json.loads(zf.read("messages.json")) if "messages.json" in zf.namelist() else []

            db_path = data_dir / "sqlite" / "zemas.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            for s in sessions:
                existing = conn.execute(
                    "SELECT session_id FROM sessions WHERE session_id = ?",
                    (s["session_id"],),
                ).fetchone()
                if not existing:
                    conn.execute(
                        """INSERT INTO sessions
                           (session_id, title, silo_account, silo_tool,
                            silo_component, status, created_at, updated_at,
                            message_count)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            s["session_id"], s["title"],
                            s.get("silo_account", ""), s.get("silo_tool", ""),
                            s.get("silo_component", ""), s.get("status", "active"),
                            s["created_at"], s["updated_at"],
                            s.get("message_count", 0),
                        ),
                    )
                    stats["sessions_added"] += 1

            for m in messages:
                existing = conn.execute(
                    "SELECT rowid FROM messages WHERE session_id = ? AND created_at = ? AND agent = ?",
                    (m["session_id"], m["created_at"], m.get("agent", "")),
                ).fetchone()
                if not existing:
                    conn.execute(
                        """INSERT INTO messages
                           (session_id, agent, content, contribution_type,
                            addressed_to, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            m["session_id"], m.get("agent", ""),
                            m.get("content", ""), m.get("contribution_type", ""),
                            m.get("addressed_to", ""), m["created_at"],
                        ),
                    )
                    stats["messages_added"] += 1

            conn.commit()
            conn.close()

        # Import ChromaDB files
        if merge_manuals:
            chroma_dir = data_dir / "chroma_db"
            chroma_dir.mkdir(parents=True, exist_ok=True)
            for name in zf.namelist():
                if name.startswith("chroma_db/") and not name.endswith("/"):
                    dest = data_dir / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
                    stats["chroma_files"] += 1

    logger.info("Imported from %s: %s", input_path, stats)
    return stats


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="ZEMAS Knowledge Export/Import")
    sub = parser.add_subparsers(dest="command")

    exp = sub.add_parser("export", help="Export knowledge to ZIP")
    exp.add_argument("--output", required=True, help="Output ZIP path")
    exp.add_argument("--data-dir", default="data", help="ZEMAS data directory")
    exp.add_argument("--no-manuals", action="store_true")
    exp.add_argument("--no-cases", action="store_true")

    imp = sub.add_parser("import", help="Import knowledge from ZIP")
    imp.add_argument("--input", required=True, help="Input ZIP path")
    imp.add_argument("--data-dir", default="data", help="ZEMAS data directory")

    args = parser.parse_args()

    if args.command == "export":
        stats = export_knowledge(
            Path(args.data_dir), Path(args.output),
            include_manuals=not args.no_manuals,
            include_cases=not args.no_cases,
        )
        print(f"Exported: {stats}")
    elif args.command == "import":
        stats = import_knowledge(Path(args.data_dir), Path(args.input))
        print(f"Imported: {stats}")
    else:
        parser.print_help()
        sys.exit(1)
