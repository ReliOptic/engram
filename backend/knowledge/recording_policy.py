"""VectorDB recording policy — chunk builders for ZEMAS.

Builds structured chunks for storage in ChromaDB:
- Type A (case_record): LLM-structured case summary on close
- Type B (conversation_trace): Raw conversation + tacit signals, never merged
- Type C (weekly_report): Parsed weekly report row with issue threading

Spec reference: scaffolding-plan-v3.md Section 5.1
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from backend.agents.orchestrator import AgentResponse


def build_silo_key(account: str, tool: str, component: str) -> str:
    """Build silo key in {account}_{tool}_{component} format."""
    return f"{account}_{tool}_{component}"


def build_type_a_chunk(
    case_metadata: dict,
    conversation: list[AgentResponse],
) -> dict:
    """Build Type A (case_record) chunk from case metadata and conversation.

    Type A is a structured summary created on case close.
    Used for similarity search when new cases come in.
    """
    case_id = case_metadata["case_id"]
    account = case_metadata["account"]
    tool = case_metadata["tool"]
    component = case_metadata["component"]

    # Build document text from conversation summary
    doc_parts = [
        f"Case: {case_id}",
        f"Title: {case_metadata.get('title', '')}",
        f"Account: {account} | Tool: {tool} | Component: {component}",
        f"Resolution: {case_metadata.get('resolution', '')}",
        "",
        "Agent Discussion Summary:",
    ]
    for resp in conversation:
        doc_parts.append(f"[{resp.agent.upper()}] {resp.content}")

    document = "\n".join(doc_parts)

    return {
        "id": f"case-{case_id}",
        "document": document,
        "metadata": {
            "chunk_type": "case_record",
            "case_id": case_id,
            "account": account,
            "tool": tool,
            "component": component,
            "silo_key": build_silo_key(account, tool, component),
            "title": case_metadata.get("title", ""),
            "resolution": case_metadata.get("resolution", ""),
            "created_at": datetime.now(tz=UTC).isoformat(),
            "agent_count": len(set(r.agent for r in conversation)),
            "message_count": len(conversation),
        },
    }


def build_type_b_chunk(
    case_metadata: dict,
    conversation: list[AgentResponse],
) -> dict:
    """Build Type B (conversation_trace) chunk from raw conversation.

    Type B is the raw conversation trace, never merged during dedup.
    Used for tacit knowledge extraction and audit.
    """
    case_id = case_metadata["case_id"]

    # Full conversation as raw text
    doc_parts = []
    for resp in conversation:
        doc_parts.append(
            f"[{resp.agent.upper()}] ({resp.contribution_type}) "
            f"→ {resp.addressed_to}: {resp.content}"
        )

    document = "\n\n".join(doc_parts)

    return {
        "id": f"trace-{case_id}",
        "document": document,
        "metadata": {
            "chunk_type": "conversation_trace",
            "case_id": case_id,
            "account": case_metadata.get("account", ""),
            "tool": case_metadata.get("tool", ""),
            "component": case_metadata.get("component", ""),
            "silo_key": build_silo_key(
                case_metadata.get("account", ""),
                case_metadata.get("tool", ""),
                case_metadata.get("component", ""),
            ),
            "created_at": datetime.now(tz=UTC).isoformat(),
            "message_count": len(conversation),
            "never_merge": True,
        },
    }


def build_type_c_chunk(row_data: dict) -> dict:
    """Build Type C (weekly_report) chunk from a parsed weekly report row.

    Type C represents a single issue entry from a weekly report.
    Issue threading links the same issue across calendar weeks.
    """
    cw = row_data["cw"]
    account = row_data.get("account", "")
    tool = row_data.get("tool", "")
    title = row_data.get("title", "")
    fob = row_data.get("fob", "")
    status = row_data.get("status", "")
    next_plan = row_data.get("next_plan", "")

    # Infer component from title if not provided
    component = row_data.get("component", "")
    if not component:
        component = _infer_component_from_title(title)

    # Build document text
    doc_parts = [
        f"[{cw}] {account} {fob} {tool}",
        f"Title: {title}",
        f"Status: {status}",
    ]
    if next_plan:
        doc_parts.append(f"Next Plan: {next_plan}")

    document = "\n".join(doc_parts)

    # Build deterministic issue_thread_id from account+tool+normalized title
    thread_id = _build_thread_id(account, tool, title)

    # Deterministic chunk ID for upsert
    chunk_id = f"weekly-{cw}-{account}-{tool}-{hashlib.sha256(title.encode()).hexdigest()[:8]}"

    return {
        "id": chunk_id,
        "document": document,
        "metadata": {
            "chunk_type": "weekly_report",
            "cw": cw,
            "account": account,
            "tool": tool,
            "component": component,
            "fob": fob,
            "silo_key": build_silo_key(account, tool, component) if component else f"{account}_{tool}",
            "title": title,
            "status": status,
            "issue_thread_id": thread_id,
        },
    }


def _build_thread_id(account: str, tool: str, title: str) -> str:
    """Build deterministic issue thread ID.

    Normalizes the title to group similar issues across weeks.
    E.g., "SECS/GEM 300 bug after SW upgrade" and
    "SECS/GEM 300 bug after SW 5.6.2 upgrade" should get the same thread.
    """
    # Normalize: lowercase, remove version numbers, collapse whitespace
    normalized = title.lower()
    normalized = re.sub(r"\d+\.\d+(\.\d+)?", "", normalized)  # Remove version numbers
    normalized = re.sub(r"\s+", " ", normalized).strip()

    key = f"{account}_{tool}_{normalized}"
    return f"thread-{hashlib.sha256(key.encode()).hexdigest()[:12]}"


def _infer_component_from_title(title: str) -> str:
    """Best-effort component inference from issue title."""
    title_lower = title.lower()
    component_keywords = {
        "InCell": ["incell", "in-cell", "in cell"],
        "Optics": ["optics", "optical", "lens", "mirror"],
        "Stage": ["stage", "wafer stage", "reticle stage"],
        "SECS/GEM": ["secs", "gem", "secs/gem", "300"],
        "Software": ["software", "sw ", "firmware", "sw upgrade"],
        "Detector": ["detector", "ccd", "sensor"],
    }
    for component, keywords in component_keywords.items():
        if any(kw in title_lower for kw in keywords):
            return component
    return ""
