"""Engram Sync Server — runs on a mini PC on the LAN.

Receives case events from Engram clients, stores them in a merged
SQLite database, and serves them to other clients on pull. No auth,
no TLS — trust-based, LAN-only.

Usage:
    uvicorn sync_server.main:app --host 0.0.0.0 --port 9000
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

DATA_DIR = Path(os.getenv("SYNC_DATA_DIR", "./sync_data"))
DB_PATH = DATA_DIR / "sync.db"

app = FastAPI(title="Engram Sync Server", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Schema ---

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device TEXT NOT NULL,
    event_type TEXT NOT NULL,
    collection TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    client_created_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_received ON events(received_at);
CREATE INDEX IF NOT EXISTS idx_events_collection ON events(collection);
CREATE INDEX IF NOT EXISTS idx_events_device ON events(device);
"""


def _get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# --- Models ---

class SyncEvent(BaseModel):
    event_type: str
    collection: str
    entity_id: str
    payload: dict
    created_at: str


class PushRequest(BaseModel):
    device: str
    events: list[SyncEvent]


# --- Endpoints ---

@app.get("/sync/status")
async def status():
    db = _get_db()
    total = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    devices = [
        r[0] for r in
        db.execute("SELECT DISTINCT device FROM events").fetchall()
    ]
    db.close()
    return {
        "status": "ok",
        "total_events": total,
        "devices": devices,
        "server_time": datetime.now(tz=UTC).isoformat(),
    }


@app.post("/sync/push")
async def push(req: PushRequest):
    db = _get_db()
    now = datetime.now(tz=UTC).isoformat()
    inserted = 0
    for event in req.events:
        # Deduplicate by entity_id + event_type + device
        existing = db.execute(
            """SELECT id FROM events
               WHERE entity_id = ? AND event_type = ? AND device = ?""",
            (event.entity_id, event.event_type, req.device),
        ).fetchone()
        if existing:
            # Update payload if newer
            db.execute(
                """UPDATE events SET payload = ?, client_created_at = ?, received_at = ?
                   WHERE id = ?""",
                (json.dumps(event.payload), event.created_at, now, existing["id"]),
            )
        else:
            db.execute(
                """INSERT INTO events
                   (device, event_type, collection, entity_id, payload,
                    client_created_at, received_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    req.device,
                    event.event_type,
                    event.collection,
                    event.entity_id,
                    json.dumps(event.payload),
                    event.created_at,
                    now,
                ),
            )
            inserted += 1
    db.commit()
    db.close()
    return {"received": len(req.events), "inserted": inserted}


@app.get("/sync/pull")
async def pull(since: str | None = None, exclude_device: str | None = None):
    db = _get_db()
    conditions = []
    params: list = []

    if since:
        conditions.append("received_at > ?")
        params.append(since)
    if exclude_device:
        conditions.append("device != ?")
        params.append(exclude_device)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    rows = db.execute(
        f"""SELECT event_type, collection, entity_id, payload,
                   client_created_at, device
            FROM events {where}
            ORDER BY received_at""",
        params,
    ).fetchall()
    db.close()

    result: dict[str, list] = {"cases": [], "traces": [], "sessions": [], "manuals": []}
    for r in rows:
        collection = r["collection"]
        entry = {
            "event_type": r["event_type"],
            "entity_id": r["entity_id"],
            "payload": json.loads(r["payload"]),
            "created_at": r["client_created_at"],
            "device": r["device"],
        }
        if collection in result:
            result[collection].append(entry)
        else:
            result.setdefault(collection, []).append(entry)

    return result


@app.get("/sync/dashboard", response_class=HTMLResponse)
async def dashboard():
    db = _get_db()

    # Stats by device
    device_stats = db.execute(
        """SELECT device,
                  COUNT(*) as total,
                  COUNT(DISTINCT entity_id) as unique_entities,
                  MAX(received_at) as last_sync
           FROM events
           GROUP BY device
           ORDER BY last_sync DESC"""
    ).fetchall()

    # Recent cases
    recent = db.execute(
        """SELECT device, entity_id, event_type, client_created_at,
                  json_extract(payload, '$.title') as title,
                  json_extract(payload, '$.account') as account,
                  json_extract(payload, '$.tool') as tool
           FROM events
           WHERE event_type = 'case_closed'
           ORDER BY received_at DESC
           LIMIT 20"""
    ).fetchall()

    db.close()

    # Build HTML
    device_rows = ""
    for d in device_stats:
        device_rows += f"""
        <tr>
            <td><strong>{d['device']}</strong></td>
            <td>{d['total']}</td>
            <td>{d['unique_entities']}</td>
            <td>{d['last_sync'][:19] if d['last_sync'] else '-'}</td>
        </tr>"""

    case_rows = ""
    for r in recent:
        title = r["title"] or r["entity_id"][:20]
        case_rows += f"""
        <tr>
            <td>{r['device']}</td>
            <td>{r['account'] or '-'}</td>
            <td>{r['tool'] or '-'}</td>
            <td>{title}</td>
            <td>{r['client_created_at'][:16] if r['client_created_at'] else '-'}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Engram Team Dashboard</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; margin: 40px; background: #f5f5f5; }}
        h1 {{ color: #141E8C; }}
        table {{ border-collapse: collapse; width: 100%; background: white;
                 box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 30px; }}
        th {{ background: #141E8C; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background: #f0f4ff; }}
        .header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 30px; }}
        .badge {{ background: #4CAF50; color: white; padding: 4px 12px;
                  border-radius: 12px; font-size: 13px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Engram Team Dashboard</h1>
        <span class="badge">LIVE</span>
    </div>

    <h2>Devices</h2>
    <table>
        <tr><th>Device</th><th>Events</th><th>Unique Items</th><th>Last Sync</th></tr>
        {device_rows or '<tr><td colspan="4">No devices connected yet</td></tr>'}
    </table>

    <h2>Recent Cases</h2>
    <table>
        <tr><th>AE</th><th>Account</th><th>Tool</th><th>Title</th><th>Date</th></tr>
        {case_rows or '<tr><td colspan="5">No cases resolved yet</td></tr>'}
    </table>

    <p style="color:#999; font-size:12px;">
        Auto-refresh: add <code>?refresh=30</code> to URL for 30s auto-reload.
        <script>
            const p = new URLSearchParams(location.search);
            if (p.has('refresh')) setTimeout(() => location.reload(), parseInt(p.get('refresh'))*1000);
        </script>
    </p>
</body>
</html>"""
