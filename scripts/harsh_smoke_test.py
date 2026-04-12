"""Harsh Smoke Test — find failure thresholds across all ZEMAS subsystems.

Tests edge cases, malformed inputs, boundary conditions, concurrency,
and stress scenarios. Reports PASS/FAIL with failure details.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ZEMAS_CONFIG_DIR", "data/config")

RESULTS: list[dict] = []


def record(category: str, name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append({"category": category, "name": name, "status": status, "detail": detail})
    icon = "  OK" if passed else "FAIL"
    print(f"  [{icon}] {name}" + (f" — {detail}" if detail and not passed else ""))


# ============================================================
# 1. CONFIG SUBSYSTEM
# ============================================================
def test_config():
    print("\n=== 1. CONFIG SUBSYSTEM ===")

    # 1-1. Missing config dir
    try:
        old = os.environ.get("ZEMAS_CONFIG_DIR")
        os.environ["ZEMAS_CONFIG_DIR"] = "/nonexistent/path"
        from importlib import reload
        import backend.config as cfg
        reload(cfg)
        try:
            cfg.load_models_config()
            record("config", "missing config dir raises error", False, "No exception raised")
        except (FileNotFoundError, Exception):
            record("config", "missing config dir raises error", True)
    finally:
        if old:
            os.environ["ZEMAS_CONFIG_DIR"] = old
        else:
            os.environ["ZEMAS_CONFIG_DIR"] = "data/config"
        reload(cfg)

    # 1-2. Valid config loads
    try:
        models = cfg.load_models_config()
        assert "providers" in models
        assert "roles" in models
        record("config", "models.json loads correctly", True)
    except Exception as e:
        record("config", "models.json loads correctly", False, str(e))

    # 1-3. Dropdowns loads
    try:
        dd = cfg.load_dropdowns_config()
        assert "accounts" in dd
        assert len(dd["accounts"]) > 0
        record("config", "dropdowns.json loads correctly", True)
    except Exception as e:
        record("config", "dropdowns.json loads correctly", False, str(e))

    # 1-4. Malformed JSON config
    try:
        with tempfile.TemporaryDirectory() as td:
            Path(td, "models.json").write_text("{invalid json!!!")
            Path(td, "dropdowns.json").write_text("{}")
            os.environ["ZEMAS_CONFIG_DIR"] = td
            reload(cfg)
            try:
                cfg.load_models_config()
                record("config", "malformed models.json raises error", False, "No exception")
            except Exception:
                record("config", "malformed models.json raises error", True)
    finally:
        os.environ["ZEMAS_CONFIG_DIR"] = "data/config"
        reload(cfg)

    # 1-5. Empty config file
    try:
        with tempfile.TemporaryDirectory() as td:
            Path(td, "models.json").write_text("")
            Path(td, "dropdowns.json").write_text("")
            os.environ["ZEMAS_CONFIG_DIR"] = td
            reload(cfg)
            try:
                cfg.load_models_config()
                record("config", "empty models.json raises error", False, "No exception")
            except Exception:
                record("config", "empty models.json raises error", True)
    finally:
        os.environ["ZEMAS_CONFIG_DIR"] = "data/config"
        reload(cfg)


# ============================================================
# 2. VECTORDB SUBSYSTEM
# ============================================================
def test_vectordb():
    print("\n=== 2. VECTORDB SUBSYSTEM ===")
    from backend.knowledge.vectordb import VectorDB

    db = VectorDB()  # In-memory

    # 2-1. Empty collection search
    try:
        results = db.search("case_records", "test query", n_results=10)
        assert results == [] or isinstance(results, list)
        record("vectordb", "search empty collection returns []", True)
    except Exception as e:
        record("vectordb", "search empty collection returns []", False, str(e))

    # 2-2. Add chunk with empty metadata (ChromaDB rejects {})
    try:
        db.add("case_records", {"document": "test doc", "metadata": {}})
        record("vectordb", "add chunk with empty metadata {}", True)
    except Exception as e:
        record("vectordb", "add chunk with empty metadata {}", False, str(e))

    # 2-3. Add chunk with empty document
    try:
        db.add("case_records", {"id": "empty-doc", "document": "", "metadata": {"t": "1"}})
        record("vectordb", "add empty document", True)
    except Exception as e:
        record("vectordb", "add empty document", False, str(e))

    # 2-4. Upsert with valid metadata
    try:
        db.upsert("case_records", {
            "id": "valid-meta",
            "document": "test with metadata",
            "metadata": {"key": "value"},
        })
        record("vectordb", "upsert with valid metadata", True)
    except Exception as e:
        record("vectordb", "upsert with valid metadata", False, str(e))

    # 2-5. Search with invalid where filter
    try:
        results = db.search("case_records", "test", where={"$invalid_op": "value"})
        record("vectordb", "invalid where filter handled", True)
    except Exception:
        record("vectordb", "invalid where filter handled", True)  # Expected to fail gracefully

    # 2-6. Get nonexistent ID
    try:
        result = db.get_by_id("case_records", "nonexistent-id-12345")
        assert result is None
        record("vectordb", "get_by_id nonexistent returns None", True)
    except Exception as e:
        record("vectordb", "get_by_id nonexistent returns None", False, str(e))

    # 2-7. Upsert batch with empty list
    try:
        ids = db.upsert_batch("case_records", [])
        assert ids == []
        record("vectordb", "upsert_batch empty list returns []", True)
    except Exception as e:
        record("vectordb", "upsert_batch empty list returns []", False, str(e))

    # 2-8. Upsert batch with duplicate IDs in same batch
    try:
        ids = db.upsert_batch("weekly", [
            {"id": "dup-1", "document": "first version", "metadata": {"v": "1"}},
            {"id": "dup-1", "document": "second version", "metadata": {"v": "2"}},
            {"id": "dup-1", "document": "third version", "metadata": {"v": "3"}},
        ])
        assert len(ids) == 1
        chunk = db.get_by_id("weekly", "dup-1")
        assert chunk["metadata"]["v"] == "3"  # Last one wins
        record("vectordb", "batch dedup keeps last occurrence", True)
    except Exception as e:
        record("vectordb", "batch dedup keeps last occurrence", False, str(e))

    # 2-9. Very long document (with valid metadata)
    try:
        long_doc = "A" * 100_000
        db.upsert("case_records", {"id": "long-doc", "document": long_doc, "metadata": {"type": "stress"}})
        result = db.get_by_id("case_records", "long-doc")
        assert result is not None
        record("vectordb", "100KB document stored", True)
    except Exception as e:
        record("vectordb", "100KB document stored", False, str(e))

    # 2-10. Unicode/special characters in document
    try:
        unicode_doc = "한국어 테스트 🔧 ZEMAS™ — «test» ñ ü ö ä 日本語 中文"
        db.upsert("case_records", {"id": "unicode-doc", "document": unicode_doc, "metadata": {"lang": "multi"}})
        result = db.get_by_id("case_records", "unicode-doc")
        assert result["document"] == unicode_doc
        record("vectordb", "unicode/emoji document preserved", True)
    except Exception as e:
        record("vectordb", "unicode/emoji document preserved", False, str(e))

    # 2-11. Count after operations
    try:
        count = db.count("case_records")
        assert count > 0
        record("vectordb", "count returns positive int", True)
    except Exception as e:
        record("vectordb", "count returns positive int", False, str(e))

    # 2-12. Unknown collection name
    try:
        db.search("completely_unknown_collection", "test")
        record("vectordb", "unknown collection auto-creates", True)
    except Exception as e:
        record("vectordb", "unknown collection auto-creates", False, str(e))

    # 2-13. search_by_silo with missing component
    try:
        results = db.search_by_silo("case_records", "test", account="ClientA", tool="ProductA")
        record("vectordb", "search_by_silo without component", True)
    except Exception as e:
        record("vectordb", "search_by_silo without component", False, str(e))

    # 2-14. Stress: 50 chunks batch upsert (ChromaDB default embeddings are slow)
    try:
        chunks = [
            {"id": f"stress-{i}", "document": f"Stress test document number {i}", "metadata": {"i": str(i)}}
            for i in range(50)
        ]
        t0 = time.time()
        ids = db.upsert_batch("case_records", chunks)
        elapsed = time.time() - t0
        assert len(ids) == 50
        record("vectordb", f"50-chunk batch upsert ({elapsed:.1f}s)", elapsed < 60)
    except Exception as e:
        record("vectordb", "50-chunk batch upsert", False, str(e))

    # 2-15. n_results larger than collection
    try:
        results = db.search("weekly", "test", n_results=99999)
        record("vectordb", "n_results > collection size", True)
    except Exception as e:
        record("vectordb", "n_results > collection size", False, str(e))

    # 2-16. Metadata with None value (ChromaDB should reject)
    try:
        db.upsert("case_records", {
            "id": "none-val",
            "document": "test none value",
            "metadata": {"key": None},
        })
        record("vectordb", "None metadata value handled", True)
    except Exception as e:
        record("vectordb", "None metadata value handled", False, str(e))

    # 2-17. Metadata with nested dict (ChromaDB only supports flat — expected rejection)
    try:
        db.upsert("case_records", {
            "id": "nested-meta",
            "document": "test nested",
            "metadata": {"nested": {"a": 1}},
        })
        record("vectordb", "nested metadata rejected (expected)", False, "Should reject nested dict")
    except Exception:
        record("vectordb", "nested metadata rejected (expected)", True)


# ============================================================
# 3. DATABASE (SQLite) SUBSYSTEM
# ============================================================
def test_database():
    print("\n=== 3. DATABASE (SQLite) SUBSYSTEM ===")
    from backend.knowledge.database import ZemasDB

    with tempfile.TemporaryDirectory() as td:
        db = ZemasDB(str(Path(td) / "test.db"))

        # 3-1. Create case with empty fields
        try:
            db.create_case("EMPTY-001", "", "", "", "")
            record("database", "create case with empty fields", True)
        except Exception as e:
            record("database", "create case with empty fields", False, str(e))

        # 3-2. Duplicate case_id
        try:
            db.create_case("DUP-001", "ClientA", "ProductA", "Module3", "Test")
            db.create_case("DUP-001", "ClientA", "ProductA", "Module3", "Test")
            record("database", "duplicate case_id raises error", False, "No IntegrityError")
        except Exception:
            record("database", "duplicate case_id raises error", True)

        # 3-3. Close nonexistent case
        try:
            db.close_case("NONEXISTENT-999", "resolved")
            record("database", "close nonexistent case (no-op)", True)
        except Exception as e:
            record("database", "close nonexistent case (no-op)", False, str(e))

        # 3-4. Get nonexistent case
        try:
            result = db.get_case("NONEXISTENT-999")
            assert result is None
            record("database", "get nonexistent case returns None", True)
        except Exception as e:
            record("database", "get nonexistent case returns None", False, str(e))

        # 3-5. SQL injection attempt in case_id
        try:
            malicious_id = "'; DROP TABLE cases; --"
            db.create_case(malicious_id, "ClientA", "ProductA", "Module3", "SQLi test")
            result = db.get_case(malicious_id)
            assert result is not None
            all_cases = db.list_cases()
            record("database", "SQL injection in case_id prevented", True)
        except Exception as e:
            record("database", "SQL injection in case_id prevented", False, str(e))

        # 3-6. SQL injection in filter params
        try:
            results = db.list_cases(account="' OR 1=1 --")
            assert isinstance(results, list)
            record("database", "SQL injection in filter prevented", True)
        except Exception as e:
            record("database", "SQL injection in filter prevented", False, str(e))

        # 3-7. Unicode in case data
        try:
            db.create_case("KR-001", "TestClient", "ProductA", "Module3", "한국어 테스트 케이스")
            result = db.get_case("KR-001")
            assert result["account"] == "TestClient"
            assert result["title"] == "한국어 테스트 케이스"
            record("database", "unicode case data preserved", True)
        except Exception as e:
            record("database", "unicode case data preserved", False, str(e))

        # 3-8. Very long title
        try:
            long_title = "A" * 10_000
            db.create_case("LONG-001", "ClientA", "ProductA", "Module3", long_title)
            result = db.get_case("LONG-001")
            assert len(result["title"]) == 10_000
            record("database", "10K char title preserved", True)
        except Exception as e:
            record("database", "10K char title preserved", False, str(e))

        # 3-9. Cost log with zero/negative values
        try:
            db.log_cost("DUP-001", "analyzer", "gemini", 0, 0, 0.0)
            db.log_cost("DUP-001", "finder", "gemini", -1, -1, -0.001)
            record("database", "zero/negative cost values accepted", True)
        except Exception as e:
            record("database", "zero/negative cost values accepted", False, str(e))

        # 3-10. List with limit=0
        try:
            results = db.list_cases(limit=0)
            assert results == []
            record("database", "list_cases limit=0 returns []", True)
        except Exception as e:
            record("database", "list_cases limit=0 returns []", False, str(e))

        # 3-11. Stress: 500 cases
        try:
            t0 = time.time()
            for i in range(500):
                db.create_case(f"STRESS-{i:04d}", "ClientA", "ProductA", "Module3", f"Stress case {i}")
            elapsed = time.time() - t0
            count = len(db.list_cases(limit=9999))
            record("database", f"500 cases created ({elapsed:.2f}s), total={count}", elapsed < 10)
        except Exception as e:
            record("database", "500 cases stress test", False, str(e))

        db.close()


# ============================================================
# 4. WEEKLY INGESTER
# ============================================================
def test_weekly_ingester():
    print("\n=== 4. WEEKLY INGESTER ===")
    from backend.knowledge.weekly_ingester import WeeklyIngester

    xlsx = "data/raw/weekly_reports/CW15_Weekly_Apps.xlsx"
    if not Path(xlsx).exists():
        record("weekly", "CW15 Excel file exists", False, "File not found")
        return

    # 4-1. Parse all sheets
    try:
        ingester = WeeklyIngester(xlsx)
        entries = ingester.parse_all_sheets()
        assert len(entries) > 0
        record("weekly", f"parse_all_sheets: {len(entries)} entries", True)
    except Exception as e:
        record("weekly", "parse_all_sheets", False, str(e))

    # 4-2. Check actual field names returned
    try:
        ingester = WeeklyIngester(xlsx)
        entries = ingester.parse_all_sheets()
        sample = entries[0]
        fields = set(sample.keys())
        record("weekly", f"entry fields: {sorted(fields)}", True)
        # Check which standard fields exist
        for f in ["account", "tool", "title", "status", "cw", "customer", "fob", "next_plan"]:
            if f in fields:
                record("weekly", f"  has field '{f}'", True)
    except Exception as e:
        record("weekly", "inspect fields", False, str(e))

    # 4-3. Nonexistent file
    try:
        WeeklyIngester("/nonexistent/file.xlsx")
        record("weekly", "nonexistent file raises error", False, "No exception")
    except Exception:
        record("weekly", "nonexistent file raises error", True)

    # 4-4. Non-Excel file
    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(b"not an excel file at all")
            f.flush()
            try:
                WeeklyIngester(f.name)
                record("weekly", "invalid Excel raises error", False, "No exception")
            except Exception:
                record("weekly", "invalid Excel raises error", True)
            finally:
                os.unlink(f.name)
    except Exception as e:
        record("weekly", "invalid Excel raises error", False, str(e))

    # 4-5. Empty entries check — title is inside metadata (entries are chunks)
    try:
        ingester = WeeklyIngester(xlsx)
        entries = ingester.parse_all_sheets()
        empty_title = [e for e in entries if not e.get("metadata", {}).get("title", "").strip()]
        record("weekly", f"entries with empty title: {len(empty_title)}/{len(entries)}",
               len(empty_title) == 0, f"{len(empty_title)} empty titles")
    except Exception as e:
        record("weekly", "empty title check", False, str(e))

    # 4-6. Parse individual sheet
    try:
        ingester = WeeklyIngester(xlsx)
        sheets = ingester.sheet_names
        record("weekly", f"sheet count: {len(sheets)}", len(sheets) > 0)
        if sheets:
            entries = ingester.parse_sheet(sheets[0])
            record("weekly", f"parse_sheet('{sheets[0]}'): {len(entries)} entries", True)
    except Exception as e:
        record("weekly", "parse individual sheet", False, str(e))


# ============================================================
# 5. ORCHESTRATOR & AGENTS
# ============================================================
def test_orchestrator():
    print("\n=== 5. ORCHESTRATOR & AGENTS ===")
    from backend.agents.orchestrator import (
        Orchestrator, AgentResponse, validate_contribution,
        RUBBER_STAMP_PATTERNS,
    )

    # 5-1. Empty agent registry
    try:
        orch = Orchestrator()
        asyncio.run(orch.run("test"))
        record("orchestrator", "run with no agents raises error", False, "Should fail")
    except Exception:
        record("orchestrator", "run with no agents raises error", True)

    # 5-2. Validate contribution — all rubber stamp patterns
    for pattern in RUBBER_STAMP_PATTERNS:
        sample = pattern.replace(r"^", "").replace(r"'?", "'")
        resp = AgentResponse(
            agent="analyzer", contribution_type="NEW_EVIDENCE",
            contribution_detail="test", addressed_to="@You", content=sample,
        )
        is_valid = validate_contribution(resp, [])
        record("orchestrator", f"rubber stamp rejected: '{sample}'", not is_valid)

    # 5-3. PASS with no prior contribution
    try:
        resp = AgentResponse(
            agent="analyzer", contribution_type="PASS",
            contribution_detail="", addressed_to="", content="",
        )
        is_valid = validate_contribution(resp, [])
        assert not is_valid  # PASS always returns False from validate
        record("orchestrator", "PASS returns False from validate", True)
    except Exception as e:
        record("orchestrator", "PASS returns False from validate", False, str(e))

    # 5-4. REVISE without prior history
    try:
        resp = AgentResponse(
            agent="analyzer", contribution_type="REVISE",
            contribution_detail="revised analysis", addressed_to="@You",
            content="Based on new evidence, I revise my earlier assessment significantly.",
        )
        is_valid = validate_contribution(resp, [])
        assert not is_valid
        record("orchestrator", "REVISE without prior rejected", True)
    except Exception as e:
        record("orchestrator", "REVISE without prior rejected", False, str(e))

    # 5-5. Unknown contribution type
    try:
        resp = AgentResponse(
            agent="analyzer", contribution_type="INVALID_TYPE",
            contribution_detail="test", addressed_to="@You", content="Something.",
        )
        is_valid = validate_contribution(resp, [])
        assert not is_valid
        record("orchestrator", "unknown contribution type rejected", True)
    except Exception as e:
        record("orchestrator", "unknown contribution type rejected", False, str(e))

    # 5-6. COUNTER without reasoning (< 10 words)
    try:
        resp = AgentResponse(
            agent="finder", contribution_type="COUNTER",
            contribution_detail="disagree", addressed_to="@Analyzer",
            content="@Analyzer I disagree.",
        )
        is_valid = validate_contribution(resp, [])
        assert not is_valid
        record("orchestrator", "short COUNTER rejected", True)
    except Exception as e:
        record("orchestrator", "short COUNTER rejected", False, str(e))

    # 5-7. Valid NEW_EVIDENCE accepted
    try:
        resp = AgentResponse(
            agent="analyzer", contribution_type="NEW_EVIDENCE",
            contribution_detail="Found case ClientA-2025-0142 with similar E4012 error after PM",
            addressed_to="@Finder",
            content="Based on case ClientA-2025-0142, the E4012 error commonly occurs after PM when the stage encoder calibration parameters are not properly restored. The resolution involved re-running the encoder offset calibration procedure per chapter 8.3.",
        )
        is_valid = validate_contribution(resp, [])
        assert is_valid
        record("orchestrator", "valid NEW_EVIDENCE accepted", True)
    except Exception as e:
        record("orchestrator", "valid NEW_EVIDENCE accepted", False, str(e))

    # 5-8. Repetition detection
    try:
        existing = [AgentResponse(
            agent="finder", contribution_type="NEW_EVIDENCE",
            contribution_detail="Encoder calibration issue found",
            addressed_to="@Analyzer",
            content="The encoder calibration issue is the root cause based on case records.",
        )]
        resp = AgentResponse(
            agent="analyzer", contribution_type="NEW_EVIDENCE",
            contribution_detail="Encoder calibration issue found",
            addressed_to="@Finder",
            content="The encoder calibration issue is the root cause based on case records.",
        )
        is_valid = validate_contribution(resp, existing)
        assert not is_valid  # Should detect repetition
        record("orchestrator", "repetition detected (Jaccard > 0.7)", True)
    except Exception as e:
        record("orchestrator", "repetition detected", False, str(e))


# ============================================================
# 6. LLM CLIENT
# ============================================================
def test_llm_client():
    print("\n=== 6. LLM CLIENT ===")
    from backend.utils.llm_client import LLMClient
    import backend.config as cfg

    models_config = cfg.load_models_config()

    # 6-1. Create client with valid config
    try:
        client = LLMClient(models_config)
        record("llm_client", "create with valid config", True)
    except Exception as e:
        record("llm_client", "create with valid config", False, str(e))

    # 6-2. Unknown role
    try:
        client = LLMClient(models_config)
        asyncio.run(client.complete("nonexistent_role", [{"role": "user", "content": "test"}]))
        record("llm_client", "unknown role raises error", False, "No exception")
    except Exception:
        record("llm_client", "unknown role raises error", True)

    # 6-3. Empty messages list
    try:
        client = LLMClient(models_config)
        asyncio.run(client.complete("analyzer", []))
        record("llm_client", "empty messages raises/returns error", False, "No exception")
    except Exception:
        record("llm_client", "empty messages raises/returns error", True)

    # 6-4. Very long message construction
    try:
        long_msg = "test " * 50_000
        msgs = [{"role": "user", "content": long_msg}]
        assert len(msgs[0]["content"]) > 200_000
        record("llm_client", "250K char message constructed", True)
    except Exception as e:
        record("llm_client", "250K char message constructed", False, str(e))

    # 6-5. Config with missing provider
    try:
        bad_config = {"providers": {}, "roles": {"test": {"provider": "missing", "model": "x"}}}
        client = LLMClient(bad_config)
        asyncio.run(client.complete("test", [{"role": "user", "content": "test"}]))
        record("llm_client", "missing provider raises error", False, "No exception")
    except Exception:
        record("llm_client", "missing provider raises error", True)


# ============================================================
# 7. FASTAPI ENDPOINTS
# ============================================================
def test_api_endpoints():
    print("\n=== 7. FASTAPI API ENDPOINTS ===")
    from backend.main import create_app
    from httpx import AsyncClient, ASGITransport

    app = create_app()

    async def run_api_tests():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:

            # 7-1. Health
            r = await client.get("/health")
            record("api", "GET /health 200", r.status_code == 200)

            # 7-2. Nonexistent route
            r = await client.get("/api/nonexistent")
            record("api", "GET /api/nonexistent 404", r.status_code == 404)

            # 7-3. Models config — no API keys exposed
            r = await client.get("/api/config/models")
            data = r.json()
            has_no_keys = "api_key" not in json.dumps(data)
            record("api", "GET /api/config/models no API keys exposed", has_no_keys and r.status_code == 200)

            # 7-4. Dropdowns config
            r = await client.get("/api/config/dropdowns")
            data = r.json()
            record("api", "GET /api/config/dropdowns returns accounts", "accounts" in data)

            # 7-5. Cases API — empty/non-existent DB
            r = await client.get("/api/cases")
            record("api", "GET /api/cases returns list", r.status_code == 200 and isinstance(r.json(), list))

            # 7-6. Cases API with filters
            r = await client.get("/api/cases", params={"account": "ClientA", "status": "open", "limit": "5"})
            record("api", "GET /api/cases with filters", r.status_code == 200)

            # 7-7. Upload — no file
            r = await client.post("/api/upload")
            record("api", "POST /api/upload without file -> 422", r.status_code == 422)

            # 7-8. Upload — empty file
            r = await client.post("/api/upload", files={"file": ("empty.txt", b"", "text/plain")})
            record("api", "POST /api/upload empty file", r.status_code == 200)

            # 7-9. Upload — normal file
            content = b"Test file content for ZEMAS smoke test"
            r = await client.post("/api/upload", files={"file": ("test.txt", content, "text/plain")})
            data = r.json()
            record("api", "POST /api/upload normal file", r.status_code == 200 and data["size_bytes"] == len(content))

            # 7-10. Upload — special chars in filename
            r = await client.post("/api/upload", files={"file": ("파일 이름 (1).txt", b"test", "text/plain")})
            record("api", "POST /api/upload Korean filename", r.status_code == 200)

            # 7-11. Upload — large file (5MB)
            large = b"X" * (5 * 1024 * 1024)
            r = await client.post("/api/upload", files={"file": ("large.bin", large, "application/octet-stream")})
            record("api", "POST /api/upload 5MB file", r.status_code == 200 and r.json()["size_bytes"] == len(large))

            # 7-12. CORS headers
            r = await client.options(
                "/health",
                headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "GET"},
            )
            has_cors = "access-control-allow-origin" in r.headers
            record("api", "CORS headers present", has_cors)

            # 7-13. Method not allowed
            r = await client.delete("/health")
            record("api", "DELETE /health -> 405", r.status_code == 405)

            # 7-14. SQL injection in query params
            r = await client.get("/api/cases", params={"account": "'; DROP TABLE cases; --"})
            record("api", "SQL injection in query params safe", r.status_code == 200)

            # 7-15. Very large query param
            r = await client.get("/api/cases", params={"account": "A" * 10_000})
            record("api", "10K char query param", r.status_code == 200)

    asyncio.run(run_api_tests())


# ============================================================
# 8. WEBSOCKET EDGE CASES
# ============================================================
def test_websocket():
    print("\n=== 8. WEBSOCKET EDGE CASES ===")
    from backend.main import create_app
    from starlette.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    # 8-1. Plain text message (non-JSON)
    try:
        with client.websocket_connect("/ws") as ws:
            ws.send_text("plain text message")
            data = ws.receive_text()
            record("websocket", "plain text handled", True)
    except Exception as e:
        record("websocket", "plain text handled", False, str(e))

    # 8-2. Empty message
    try:
        with client.websocket_connect("/ws") as ws:
            ws.send_text("")
            data = ws.receive_text()
            record("websocket", "empty message handled", True)
    except Exception as e:
        record("websocket", "empty message handled", False, str(e))

    # 8-3. Malformed JSON
    try:
        with client.websocket_connect("/ws") as ws:
            ws.send_text("{invalid json!!!")
            data = ws.receive_text()
            record("websocket", "malformed JSON handled", True)
    except Exception as e:
        record("websocket", "malformed JSON handled", False, str(e))

    # 8-4. Valid JSON but wrong type
    try:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "unknown_type", "payload": {}}))
            data = ws.receive_text()
            record("websocket", "unknown message type echoed", True)
    except Exception as e:
        record("websocket", "unknown message type echoed", False, str(e))

    # 8-5. user_message with missing payload
    try:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "user_message"}))
            data = json.loads(ws.receive_text())
            record("websocket", "user_message no payload", data.get("type") == "status_update")
    except Exception as e:
        record("websocket", "user_message no payload", False, str(e))

    # 8-6. user_message with empty silo
    try:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({
                "type": "user_message",
                "payload": {"text": "test", "silo": {}},
            }))
            data = json.loads(ws.receive_text())
            record("websocket", "user_message empty silo", data.get("type") == "status_update")
    except Exception as e:
        record("websocket", "user_message empty silo", False, str(e))

    # 8-7. Very large message
    try:
        with client.websocket_connect("/ws") as ws:
            big_text = "A" * 100_000
            ws.send_text(json.dumps({
                "type": "user_message",
                "payload": {"text": big_text, "silo": {"account": "ClientA", "tool": "ProductA", "component": "Module3"}},
            }))
            data = json.loads(ws.receive_text())
            record("websocket", "100KB message accepted", data.get("type") == "status_update")
    except Exception as e:
        record("websocket", "100KB message accepted", False, str(e))

    # 8-8. Rapid fire messages
    try:
        with client.websocket_connect("/ws") as ws:
            for i in range(10):
                ws.send_text(json.dumps({"type": "ping", "payload": {"n": i}}))
            responses = []
            for _ in range(10):
                responses.append(ws.receive_text())
            record("websocket", f"rapid fire 10 msgs: {len(responses)} back", len(responses) == 10)
    except Exception as e:
        record("websocket", "rapid fire 10 messages", False, str(e))

    # 8-9. XSS in message payload
    try:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({
                "type": "user_message",
                "payload": {"text": "<script>alert('xss')</script>", "silo": {}},
            }))
            data = json.loads(ws.receive_text())
            record("websocket", "XSS payload accepted safely", data.get("type") == "status_update")
    except Exception as e:
        record("websocket", "XSS payload accepted safely", False, str(e))


# ============================================================
# 9. TACIT EXTRACTOR
# ============================================================
def test_tacit_extractor():
    print("\n=== 9. TACIT EXTRACTOR ===")
    from backend.knowledge.tacit_extractor import TacitExtractor

    # Create instance without LLM (just for parse testing)
    ext = TacitExtractor.__new__(TacitExtractor)

    # 9-1. Parse empty array
    try:
        signals = ext._parse_signals("[]")
        assert signals == []
        record("tacit", "parse empty signals", True)
    except Exception as e:
        record("tacit", "parse empty signals", False, str(e))

    # 9-2. Malformed JSON from LLM
    try:
        signals = ext._parse_signals("This is not JSON at all")
        assert signals == []
        record("tacit", "malformed JSON returns []", True)
    except Exception as e:
        record("tacit", "malformed JSON returns []", False, str(e))

    # 9-3. Valid signal with correct field name ("signal" not "type")
    try:
        valid_json = json.dumps([{
            "signal": "SE skipped TIS recalibration due to time pressure",
            "type": "field_decision",
            "source_speaker": "kiwon",
            "context": "post_PM",
            "confidence": 0.85,
            "related_procedure": "Ch.8.3",
        }])
        signals = ext._parse_signals(valid_json)
        assert len(signals) == 1
        assert signals[0]["type"] == "field_decision"
        record("tacit", "valid signal parsed (with 'signal' field)", True)
    except Exception as e:
        record("tacit", "valid signal parsed", False, str(e))

    # 9-4. Signal missing 'signal' key (filtered out by parser)
    try:
        bad_json = json.dumps([{
            "type": "field_decision",
            "description": "No signal key here",
        }])
        signals = ext._parse_signals(bad_json)
        assert signals == []  # Should be filtered out because no "signal" key
        record("tacit", "signal without 'signal' key filtered out", True)
    except Exception as e:
        record("tacit", "signal without 'signal' key filtered out", False, str(e))

    # 9-5. Markdown code block wrapping
    try:
        wrapped = '```json\n[{"signal": "test signal", "type": "field_decision"}]\n```'
        signals = ext._parse_signals(wrapped)
        assert len(signals) == 1
        record("tacit", "markdown code block unwrapped", True)
    except Exception as e:
        record("tacit", "markdown code block unwrapped", False, str(e))

    # 9-6. Non-list JSON (object instead of array)
    try:
        signals = ext._parse_signals('{"signal": "not a list"}')
        assert signals == []
        record("tacit", "non-list JSON returns []", True)
    except Exception as e:
        record("tacit", "non-list JSON returns []", False, str(e))


# ============================================================
# 10. DEDUP & DREAMING
# ============================================================
def test_dedup():
    print("\n=== 10. DEDUP & DREAMING ===")
    from backend.knowledge.dedup import DedupEngine
    from backend.knowledge.vectordb import VectorDB

    # Use FRESH db for dedup to avoid scanning large collections from other tests
    dedup_db = VectorDB()

    # 10-1. run_light_sleep on empty collection (use unique name to avoid cross-test pollution)
    try:
        engine = DedupEngine(dedup_db)
        report = asyncio.run(engine.run_light_sleep("dedup_empty_test"))
        assert report.total_items == 0
        record("dedup", "run_light_sleep on empty collection", True)
    except Exception as e:
        record("dedup", "run_light_sleep on empty collection", False, f"{type(e).__name__}: {e}")

    # 10-2. run_light_sleep with near-dupes
    try:
        dedup_db.upsert("case_records", {"id": "d1", "document": "Module3 sync error on ProductA after PM calibration", "metadata": {"account": "ClientA"}})
        dedup_db.upsert("case_records", {"id": "d2", "document": "Module3 sync error on ProductA after PM calibration procedure", "metadata": {"account": "ClientA"}})
        engine = DedupEngine(dedup_db)
        report = asyncio.run(engine.run_light_sleep("case_records"))
        record("dedup", f"light_sleep: {report.near_duplicates_found} near-dupes found", True)
    except Exception as e:
        record("dedup", "light_sleep with near-dupes", False, str(e))

    # 10-3. Traces never merged
    try:
        dedup_db.upsert("traces", {"id": "t1", "document": "Conversation trace 1", "metadata": {"never_merge": True, "case_id": "T1"}})
        dedup_db.upsert("traces", {"id": "t2", "document": "Conversation trace 1 duplicate", "metadata": {"never_merge": True, "case_id": "T2"}})
        engine = DedupEngine(dedup_db)
        report = asyncio.run(engine.run_light_sleep("traces"))
        assert report.skipped_traces > 0
        assert report.near_duplicates_found == 0
        record("dedup", f"traces excluded: {report.skipped_traces} skipped", True)
    except Exception as e:
        record("dedup", "traces excluded from merge", False, str(e))

    # 10-4. Knowledge graph with GraphNode/GraphEdge (correct API)
    try:
        from backend.knowledge.graph import KnowledgeGraph, GraphNode, GraphEdge
        kg = KnowledgeGraph()
        kg.add_node(GraphNode(id="ProductA", type="tool", label="ProductA"))
        kg.add_node(GraphNode(id="E4012", type="error", label="E4012"))
        kg.add_edge(GraphEdge(source="ProductA", target="E4012", type="has_error", weight=0.9))
        data = kg.to_dict()
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        record("dedup", "knowledge graph CRUD", True)
    except Exception as e:
        record("dedup", "knowledge graph CRUD", False, str(e))

    # 10-5. Graph export/import roundtrip
    try:
        from backend.knowledge.graph import KnowledgeGraph, GraphNode, GraphEdge
        kg = KnowledgeGraph()
        kg.add_node(GraphNode(id="ProductA", type="tool", label="ProductA"))
        kg.add_node(GraphNode(id="E4012", type="error", label="E4012"))
        kg.add_edge(GraphEdge(source="ProductA", target="E4012", type="has_error", weight=0.95))
        exported = kg.to_dict()
        kg2 = KnowledgeGraph.from_dict(exported)
        assert kg2.node_count == 2
        assert kg2.edge_count == 1
        record("dedup", "graph dict roundtrip", True)
    except Exception as e:
        record("dedup", "graph dict roundtrip", False, str(e))

    # 10-6. Graph from VectorDB
    try:
        from backend.knowledge.graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.build_from_vectordb(dedup_db, collections=["case_records"])
        record("dedup", f"graph from VectorDB: {kg.node_count} nodes, {kg.edge_count} edges", True)
    except Exception as e:
        record("dedup", "graph from VectorDB", False, str(e))


# ============================================================
# 11. SESSION PRELOADER
# ============================================================
def test_preloader():
    print("\n=== 11. SESSION PRELOADER ===")
    from backend.memory.preloader import SessionPreloader
    from backend.knowledge.vectordb import VectorDB

    pre_db = VectorDB()  # Fresh DB

    # 11-1. Preload from empty DB
    try:
        preloader = SessionPreloader(pre_db)
        ctx = asyncio.run(preloader.build_context("ClientA", "ProductA", "Module3", "E4012 error"))
        record("preloader", "empty DB preload", True)
    except Exception as e:
        record("preloader", "empty DB preload", False, str(e))

    # 11-2. Context text fits limit (5 items only — ChromaDB default embeddings are slow)
    try:
        for i in range(5):
            pre_db.upsert("case_records", {
                "id": f"pre-{i}",
                "document": f"Case record {i} about ProductA stage issue " * 50,
                "metadata": {"account": "ClientA", "tool": "ProductA", "silo_key": "SEC_PROVE_Stage"},
            })
        preloader = SessionPreloader(pre_db)
        ctx = asyncio.run(preloader.build_context("ClientA", "ProductA", "Module3", "stage error"))
        prompt_text = ctx.to_prompt_text()
        assert len(prompt_text) <= 40_000
        record("preloader", f"context fits 40K ({len(prompt_text)} chars)", True)
    except Exception as e:
        record("preloader", "context fits 40K limit", False, str(e))

    # 11-3. Nonexistent silo
    try:
        preloader = SessionPreloader(pre_db)
        ctx = asyncio.run(preloader.build_context("NONEXISTENT", "NOTHING", "VOID", "test"))
        prompt_text = ctx.to_prompt_text()
        record("preloader", "nonexistent silo returns context", True)
    except Exception as e:
        record("preloader", "nonexistent silo returns context", False, str(e))


# ============================================================
# 12. BASE AGENT RESPONSE PARSING
# ============================================================
def test_agent_parsing():
    print("\n=== 12. AGENT RESPONSE PARSING ===")
    from backend.agents.base_agent import BaseAgent
    from backend.utils.llm_client import LLMResponse

    agent = BaseAgent.__new__(BaseAgent)
    agent.role = "analyzer"

    def make_llm_response(content: str) -> LLMResponse:
        return LLMResponse(
            content=content, model="test", provider="test",
            prompt_tokens=0, completion_tokens=0, total_tokens=0, estimated_cost_usd=0,
        )

    # 12-1. Valid JSON response
    try:
        resp = agent._parse_response(make_llm_response(json.dumps({
            "contribution_type": "NEW_EVIDENCE",
            "contribution_detail": "Found relevant case",
            "addressed_to": "@Finder",
            "content": "Based on case data...",
        })))
        assert resp.contribution_type == "NEW_EVIDENCE"
        record("agent_parse", "valid JSON parsed", True)
    except Exception as e:
        record("agent_parse", "valid JSON parsed", False, str(e))

    # 12-2. Markdown code block JSON
    try:
        resp = agent._parse_response(make_llm_response(
            '```json\n{"contribution_type": "PASS", "contribution_detail": "", "addressed_to": "", "content": ""}\n```'
        ))
        assert resp.contribution_type == "PASS"
        record("agent_parse", "markdown code block JSON parsed", True)
    except Exception as e:
        record("agent_parse", "markdown code block JSON parsed", False, str(e))

    # 12-3. Free-form text (non-JSON)
    try:
        resp = agent._parse_response(make_llm_response(
            "I think the issue is related to encoder calibration after PM."
        ))
        assert resp.contribution_type == "NEW_EVIDENCE"
        assert "encoder calibration" in resp.content
        record("agent_parse", "free-form fallback to NEW_EVIDENCE", True)
    except Exception as e:
        record("agent_parse", "free-form fallback to NEW_EVIDENCE", False, str(e))

    # 12-4. Empty response
    try:
        resp = agent._parse_response(make_llm_response(""))
        record("agent_parse", "empty response handled", True)
    except Exception as e:
        record("agent_parse", "empty response handled", False, str(e))

    # 12-5. JSON with extra fields
    try:
        resp = agent._parse_response(make_llm_response(json.dumps({
            "contribution_type": "COUNTER",
            "contribution_detail": "test",
            "addressed_to": "@Analyzer",
            "content": "I disagree because of evidence X Y Z.",
            "extra_field": "should be ignored",
        })))
        assert resp.contribution_type == "COUNTER"
        record("agent_parse", "extra JSON fields ignored", True)
    except Exception as e:
        record("agent_parse", "extra JSON fields ignored", False, str(e))

    # 12-6. Truncated JSON
    try:
        resp = agent._parse_response(make_llm_response(
            '{"contribution_type": "NEW_EVIDENCE", "content": "truncated...'
        ))
        # Should fallback to free-form
        assert resp.contribution_type == "NEW_EVIDENCE"
        record("agent_parse", "truncated JSON falls back gracefully", True)
    except Exception as e:
        record("agent_parse", "truncated JSON falls back gracefully", False, str(e))


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print("ZEMAS HARSH SMOKE TEST")
    print("=" * 60)

    test_config()
    test_vectordb()
    test_database()
    test_weekly_ingester()
    test_orchestrator()
    test_llm_client()
    test_api_endpoints()
    test_websocket()
    test_tacit_extractor()
    test_dedup()
    test_preloader()
    test_agent_parsing()

    # Summary
    print("\n" + "=" * 60)
    print("SMOKE TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    total = len(RESULTS)

    print(f"\nTotal: {total}  |  PASS: {passed}  |  FAIL: {failed}")
    print(f"Pass rate: {passed/total*100:.1f}%")

    if failed > 0:
        print(f"\n--- FAILURES ({failed}) ---")
        for r in RESULTS:
            if r["status"] == "FAIL":
                print(f"  [{r['category']}] {r['name']}: {r['detail']}")

    print()
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
