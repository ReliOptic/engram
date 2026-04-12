"""TDD tests for SQLite structured database.

SQLite complements ChromaDB: structured queries, case metadata,
cost tracking, and audit logging.
"""

import pytest

from backend.knowledge.database import EngramDB


@pytest.fixture
def db(tmp_path):
    """Create a test database in temp directory."""
    return EngramDB(db_path=str(tmp_path / "test_engram.db"))


async def test_create_case(db):
    """케이스 생성 후 ID로 조회 가능."""
    case_id = db.create_case(
        case_id="CASE-2026-0042",
        account="ClientA",
        tool="ProductA",
        component="Module1",
        title="PRV-4412 3nm offset post-PM",
    )
    assert case_id == "CASE-2026-0042"

    case = db.get_case("CASE-2026-0042")
    assert case is not None
    assert case["account"] == "ClientA"
    assert case["status"] == "open"


async def test_close_case(db):
    """케이스 종료 시 status=closed, resolution 기록."""
    db.create_case(
        case_id="CASE-2026-0042",
        account="ClientA",
        tool="ProductA",
        component="Module1",
        title="PRV-4412 offset",
    )
    db.close_case("CASE-2026-0042", resolution="TIS recalibration applied")

    case = db.get_case("CASE-2026-0042")
    assert case["status"] == "closed"
    assert case["resolution"] == "TIS recalibration applied"
    assert case["closed_at"] is not None


async def test_list_cases_by_account(db):
    """특정 account의 케이스만 필터링."""
    db.create_case(case_id="C001", account="ClientA", tool="ProductA", component="Module1", title="Issue 1")
    db.create_case(case_id="C002", account="ClientB", tool="ProductB", component="Module2", title="Issue 2")
    db.create_case(case_id="C003", account="ClientA", tool="ProductB", component="Module3", title="Issue 3")

    sec_cases = db.list_cases(account="ClientA")
    assert len(sec_cases) == 2
    assert all(c["account"] == "ClientA" for c in sec_cases)


async def test_list_open_cases(db):
    """열린 케이스만 조회."""
    db.create_case(case_id="C001", account="ClientA", tool="ProductA", component="Module1", title="Open")
    db.create_case(case_id="C002", account="ClientA", tool="ProductA", component="Module2", title="Closed")
    db.close_case("C002", resolution="Fixed")

    open_cases = db.list_cases(status="open")
    assert len(open_cases) == 1
    assert open_cases[0]["case_id"] == "C001"


async def test_log_cost(db):
    """LLM 호출 비용 기록 + 합산."""
    db.log_cost(
        case_id="C001",
        role="analyzer",
        model="google/gemini-3.1-flash-lite-preview",
        prompt_tokens=500,
        completion_tokens=200,
        cost_usd=0.0,
    )
    db.log_cost(
        case_id="C001",
        role="finder",
        model="openai/gpt-5.4",
        prompt_tokens=1000,
        completion_tokens=500,
        cost_usd=0.0075,
    )

    total = db.get_case_cost("C001")
    assert total["total_prompt_tokens"] == 1500
    assert total["total_completion_tokens"] == 700
    assert total["total_cost_usd"] == pytest.approx(0.0075)
    assert total["call_count"] == 2


async def test_cost_summary_by_model(db):
    """모델별 비용 요약."""
    db.log_cost(case_id="C001", role="analyzer", model="gemini-flash", prompt_tokens=100, completion_tokens=50, cost_usd=0.0)
    db.log_cost(case_id="C001", role="finder", model="gpt-5.4", prompt_tokens=200, completion_tokens=100, cost_usd=0.003)
    db.log_cost(case_id="C002", role="analyzer", model="gpt-5.4", prompt_tokens=300, completion_tokens=150, cost_usd=0.005)

    summary = db.get_cost_summary_by_model()
    models = {s["model"]: s for s in summary}
    assert "gpt-5.4" in models
    assert models["gpt-5.4"]["total_cost_usd"] == pytest.approx(0.008)
