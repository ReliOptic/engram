"""Sync client — pushes local changes and pulls remote updates.

Designed for offline-first: if the server is unreachable, operations
silently queue. No exceptions thrown on network failure — the UI just
shows a "pending" badge. Next time the server is reachable, everything
catches up.

The sync server is a mini PC on the LAN running FastAPI on port 9000.
No auth, no TLS (LAN-only). Add API key later when the team grows.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.sync.queue import SyncQueue

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0


class SyncClient:
    """Push/pull sync client for Engram offline-first architecture."""

    def __init__(
        self,
        server_url: str | None,
        queue: SyncQueue,
        device_name: str = "unknown",
    ):
        self.server_url = server_url.rstrip("/") if server_url else None
        self.queue = queue
        self.device_name = device_name
        self._online: bool | None = None

    @property
    def enabled(self) -> bool:
        return self.server_url is not None

    def is_online(self) -> bool:
        """Check if sync server is reachable."""
        if not self.enabled:
            return False
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{self.server_url}/sync/status")
                self._online = resp.status_code == 200
        except Exception:
            self._online = False
        return self._online or False

    async def push_pending(self) -> int:
        """Push all pending events to the sync server.

        Returns number of events successfully pushed.
        """
        if not self.enabled:
            return 0

        pending = self.queue.get_pending(limit=500)
        if not pending:
            return 0

        pushed_ids: list[int] = []
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.server_url}/sync/push",
                    json={
                        "device": self.device_name,
                        "events": [
                            {
                                "event_type": e["event_type"],
                                "collection": e["collection"],
                                "entity_id": e["entity_id"],
                                "payload": e["payload"],
                                "created_at": e["created_at"],
                            }
                            for e in pending
                        ],
                    },
                )
                if resp.status_code == 200:
                    pushed_ids = [e["id"] for e in pending]
                    self.queue.mark_synced(pushed_ids, self.server_url or "")
                    self._online = True
                    logger.info("Pushed %d events to sync server", len(pushed_ids))
                else:
                    logger.warning(
                        "Sync push failed: %d %s", resp.status_code, resp.text[:200]
                    )
        except Exception as e:
            self._online = False
            logger.debug("Sync push offline: %s", e)

        return len(pushed_ids)

    async def pull_updates(self, since: str | None = None) -> dict[str, Any]:
        """Pull new cases/manuals from server since given timestamp.

        Returns dict with keys: cases, traces, manuals (lists of chunks).
        """
        if not self.enabled:
            return {"cases": [], "traces": [], "manuals": []}

        try:
            params: dict[str, str] = {}
            if since:
                params["since"] = since
            params["exclude_device"] = self.device_name

            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(
                    f"{self.server_url}/sync/pull",
                    params=params,
                )
                if resp.status_code == 200:
                    self._online = True
                    data = resp.json()
                    logger.info(
                        "Pulled %d cases, %d traces, %d manuals from sync server",
                        len(data.get("cases", [])),
                        len(data.get("traces", [])),
                        len(data.get("manuals", [])),
                    )
                    return data
                else:
                    logger.warning("Sync pull failed: %d", resp.status_code)
        except Exception as e:
            self._online = False
            logger.debug("Sync pull offline: %s", e)

        return {"cases": [], "traces": [], "manuals": []}

    def get_status(self) -> dict[str, Any]:
        """Current sync status for frontend display."""
        pending = self.queue.pending_count()
        return {
            "enabled": self.enabled,
            "server_url": self.server_url,
            "online": self._online,
            "pending_events": pending,
            "status": (
                "disabled" if not self.enabled
                else "synced" if self._online and pending == 0
                else "pending" if pending > 0
                else "offline"
            ),
        }
