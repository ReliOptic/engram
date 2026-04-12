"""Case recorder — dual-writes case data to ChromaDB + SQLite.

When a case is closed:
- ChromaDB: Type A (case_record) + Type B (conversation_trace) for similarity search
- SQLite: Case metadata + status for structured queries

Spec reference: scaffolding-plan-v3.md Section 5.1, Section 12.5
"""

from __future__ import annotations

from backend.agents.orchestrator import AgentResponse
from backend.knowledge.database import ZemasDB
from backend.knowledge.recording_policy import build_type_a_chunk, build_type_b_chunk
from backend.knowledge.vectordb import VectorDB


class CaseRecorder:
    """Dual-write recorder: ChromaDB (search) + SQLite (structured queries).

    If a ``SyncQueue`` is provided, case close events are queued for
    push to the sync server. This is the only integration point
    between the existing ZEMAS flow and the Phase 3 sync system.
    """

    def __init__(self, vectordb: VectorDB, db: ZemasDB | None = None, sync_queue=None):
        self._vectordb = vectordb
        self._db = db
        self._sync_queue = sync_queue

    async def record_case(
        self,
        case_metadata: dict,
        conversation: list[AgentResponse],
    ) -> tuple[str, str]:
        """Record a closed case to both ChromaDB and SQLite.

        Args:
            case_metadata: Dict with case_id, account, tool, component, title, resolution.
            conversation: List of AgentResponse from the orchestrator.

        Returns:
            Tuple of (type_a_id, type_b_id).
        """
        # ChromaDB: similarity search chunks
        type_a = build_type_a_chunk(case_metadata, conversation)
        type_b = build_type_b_chunk(case_metadata, conversation)

        type_a_id = self._vectordb.upsert("case_records", type_a)
        type_b_id = self._vectordb.upsert("traces", type_b)

        # SQLite: structured metadata
        if self._db:
            case_id = case_metadata["case_id"]
            existing = self._db.get_case(case_id)
            if not existing:
                self._db.create_case(
                    case_id=case_id,
                    account=case_metadata.get("account", ""),
                    tool=case_metadata.get("tool", ""),
                    component=case_metadata.get("component", ""),
                    title=case_metadata.get("title", ""),
                )
            self._db.close_case(
                case_id=case_id,
                resolution=case_metadata.get("resolution", ""),
            )

        # Sync queue: push case_closed event for server sync
        if self._sync_queue:
            self._sync_queue.push_event(
                event_type="case_closed",
                collection="case_records",
                entity_id=case_metadata["case_id"],
                payload={
                    "case_id": case_metadata["case_id"],
                    "account": case_metadata.get("account", ""),
                    "tool": case_metadata.get("tool", ""),
                    "component": case_metadata.get("component", ""),
                    "title": case_metadata.get("title", ""),
                    "resolution": case_metadata.get("resolution", ""),
                    "type_a_chunk": type_a,
                    "type_b_chunk": type_b,
                },
            )

        return type_a_id, type_b_id
