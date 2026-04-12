"""Tests for session pre-loading (RAG context builder).

Spec reference: scaffolding-plan-v3.md Section 3.3, Section 11.2
"""

import pytest

from backend.knowledge.vectordb import VectorDB
from backend.knowledge.recording_policy import build_type_a_chunk, build_type_c_chunk
from backend.agents.orchestrator import AgentResponse
from backend.memory.preloader import SessionPreloader


@pytest.fixture
def vectordb():
    return VectorDB()  # ephemeral, no persist_dir


@pytest.fixture
def preloader(vectordb):
    return SessionPreloader(vectordb)


def _make_case(case_id, account, tool, component, title, resolution):
    """Helper to create a case in vectordb."""
    metadata = {
        "case_id": case_id,
        "account": account,
        "tool": tool,
        "component": component,
        "title": title,
        "resolution": resolution,
    }
    conversation = [
        AgentResponse(
            agent="analyzer",
            contribution_type="NEW_EVIDENCE",
            contribution_detail="test",
            addressed_to="@You",
            content=f"Analysis for {title}",
        ),
    ]
    return build_type_a_chunk(metadata, conversation)


async def test_preloads_same_tool_cases(vectordb, preloader):
    """같은 account+tool의 최근 케이스 로딩."""
    # Insert several cases for SEC PROVE
    for i in range(5):
        chunk = _make_case(f"SEC-{i}", "SEC", "PROVE", "InCell",
                           f"InCell error case {i}", f"Fixed via step {i}")
        vectordb.upsert("case_records", chunk)

    # Also insert a different account case
    other = _make_case("TSMC-1", "TSMC", "AIMS", "Optics",
                       "AIMS optics drift", "Recalibrated")
    vectordb.upsert("case_records", other)

    context = await preloader.build_context(
        account="SEC", tool="PROVE", component="InCell",
        query="InCell DB registration offset",
    )

    assert context.silo_cases  # Should have SEC PROVE cases
    assert all("SEC" in c.get("metadata", {}).get("account", "")
               for c in context.silo_cases)


async def test_preloads_cross_silo(vectordb, preloader):
    """유사 이슈 cross-silo 검색."""
    # Insert cases in different silos with similar issues
    for acc in ["SEC", "TSMC", "Intel"]:
        chunk = _make_case(f"{acc}-offset", acc, "PROVE", "InCell",
                           "DB registration offset after PM",
                           "TIS recalibration resolved")
        vectordb.upsert("case_records", chunk)

    context = await preloader.build_context(
        account="SEC", tool="PROVE", component="InCell",
        query="DB registration offset post-PM",
    )

    # Cross-silo should find similar cases from other accounts
    assert context.cross_silo_cases is not None


async def test_preload_fits_context(vectordb, preloader):
    """Pre-loaded context가 적절한 크기."""
    for i in range(20):
        chunk = _make_case(f"SEC-{i}", "SEC", "PROVE", "InCell",
                           f"Case {i}: various InCell issue",
                           f"Resolution {i}")
        vectordb.upsert("case_records", chunk)

    context = await preloader.build_context(
        account="SEC", tool="PROVE", component="InCell",
        query="InCell error troubleshooting",
    )

    # Context text should be bounded
    text = context.to_prompt_text()
    assert len(text) > 0
    # Rough check: shouldn't exceed ~50K characters (well under 256K token limit)
    assert len(text) < 50_000


async def test_preloader_includes_manuals(vectordb, preloader):
    """Pre-loader should include manual entries in context."""
    chunk = {
        "id": "manual-prove-ch8",
        "document": "Optical alignment procedure for PROVE InCell module.",
        "metadata": {
            "tool_family": "PROVE",
            "source_file": "UserManual.pdf",
            "section_title": "Chapter 8",
        },
    }
    vectordb.upsert("manuals", chunk)

    ctx = await preloader.build_context(
        account="SEC", tool="PROVE", component="InCell",
        query="optical alignment",
    )

    assert len(ctx.manual_entries) > 0
    assert "Manual / SOP References" in ctx.to_prompt_text()
