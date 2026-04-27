"""Session pre-loader — builds RAG context for new conversations.

When a user starts a new support session, pre-loads relevant context:
1. Same silo cases (account + tool + component) — most recent 10
2. Cross-silo similar cases — top 5 from other accounts
3. Related weekly report entries — top 5

Spec reference: scaffolding-plan-v3.md Section 3.3, Section 12.7
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class SessionContext:
    """Pre-loaded context for a support session."""

    silo_cases: list[dict] = field(default_factory=list)
    cross_silo_cases: list[dict] = field(default_factory=list)
    weekly_entries: list[dict] = field(default_factory=list)
    manual_entries: list[dict] = field(default_factory=list)

    def to_prompt_text(self, max_chars: int = 40_000) -> str:
        """Format context for injection into agent system prompts.

        Truncates to stay within token budget.
        """
        parts = []

        if self.silo_cases:
            parts.append("=== Related Cases (Same Tool) ===")
            for case in self.silo_cases[:10]:
                doc = case.get("document", "")
                meta = case.get("metadata", {})
                parts.append(
                    f"[Case {meta.get('case_id', '?')}] "
                    f"{meta.get('title', '')}\n{doc[:500]}"
                )

        if self.cross_silo_cases:
            parts.append("\n=== Similar Cases (Other Accounts) ===")
            for case in self.cross_silo_cases[:5]:
                doc = case.get("document", "")
                meta = case.get("metadata", {})
                parts.append(
                    f"[Case {meta.get('case_id', '?')} — {meta.get('account', '')}] "
                    f"{meta.get('title', '')}\n{doc[:300]}"
                )

        if self.weekly_entries:
            parts.append("\n=== Weekly Report References ===")
            for entry in self.weekly_entries[:5]:
                doc = entry.get("document", "")
                meta = entry.get("metadata", {})
                parts.append(
                    f"[{meta.get('cw', '')}] {meta.get('title', '')}\n{doc[:200]}"
                )

        if self.manual_entries:
            parts.append("\n=== Manual / SOP References ===")
            for entry in self.manual_entries[:5]:
                doc = entry.get("document", "")
                meta = entry.get("metadata", {})
                source = meta.get("source_file", "")
                section = meta.get("section_title", "")
                parts.append(
                    f"[{source}] {section}\n{doc[:400]}"
                )

        text = "\n\n".join(parts)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (truncated)"
        return text


class SessionPreloader:
    """Build pre-loaded context for a new support session."""

    def __init__(self, vectordb):
        self._vectordb = vectordb

    async def build_context(
        self,
        account: str,
        tool: str,
        component: str,
        query: str,
        max_silo: int = 10,
        max_cross: int = 5,
        max_weekly: int = 5,
        max_manuals: int = 5,
    ) -> SessionContext:
        """Build session context by searching VectorDB.

        Args:
            account: Customer account (e.g., "Client A").
            tool: Tool type (e.g., "Product A").
            component: Component (e.g., "InCell").
            query: User's initial query text.
            max_silo: Max same-silo cases.
            max_cross: Max cross-silo cases.
            max_weekly: Max weekly report entries.

        Returns:
            SessionContext with pre-loaded data.
        """
        where_manual = {"tool_family": tool} if tool else None

        silo_cases, all_similar, weekly_entries, manual_entries = await asyncio.gather(
            self._vectordb.async_search_by_silo(
                "case_records", query, account, tool, component, n_results=max_silo
            ),
            self._vectordb.async_search(
                "case_records", query, n_results=max_silo + max_cross
            ),
            self._vectordb.async_search("weekly", query, n_results=max_weekly),
            self._vectordb.async_search(
                "manuals", query, n_results=max_manuals, where=where_manual
            ),
        )

        context = SessionContext()
        context.silo_cases = silo_cases
        silo_ids = {c["id"] for c in context.silo_cases}
        context.cross_silo_cases = [
            c for c in all_similar if c["id"] not in silo_ids
        ][:max_cross]
        context.weekly_entries = weekly_entries
        context.manual_entries = manual_entries
        return context
