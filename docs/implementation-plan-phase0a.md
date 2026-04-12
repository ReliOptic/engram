# ZEMAS Implementation Plan — Phase 12.1 + Phase 0-A

## Context
ZEMAS (ZEISS EUV Multi-Agent Support System) greenfield project.
Phases 12.1 (CLAUDE.md) and 0-A (backend foundation) establish the skeleton for all subsequent development.

---

## Architecture Decisions (Locked In)

| Decision | Choice |
|---|---|
| LLM Providers | Both OpenRouter + OpenAI, configurable per role in models.json |
| Cost-effective model | Gemini 3.1 Flash Lite via OpenRouter |
| Power model | GPT-5.4 / Codex via OpenAI |
| Embeddings | OpenRouter embeddings |
| User scope | Single-user, no auth |
| VectorDB | ChromaDB (local persistence) |
| Structured data | SQLite alongside ChromaDB for case metadata |
| LLM abstraction | LLMClient with token/cost tracking, provider-agnostic |
| Agent delivery | Full-message Phase 0, streaming-ready for Phase 1-D |
| Frontend state | useState + context |
| Config | .env for secrets, models.json for model mapping, dropdowns.json for UI |

---

## Step 1: Project Skeleton + Dependencies
- Directory structure (backend/, data/, scripts/, tests/, frontend/, docs/)
- pyproject.toml with all Python dependencies
- .env.example with required variables
- .gitignore
- Copy CW15_Weekly_Apps.xlsx to data/raw/weekly_reports/

## Step 2: CLAUDE.md (Phase 12.1)
- Project constitution with principles, rules, structure, policies

## Step 3: Config Files
- data/config/models.json — role → provider → model mapping
- data/config/dropdowns.json — Account → Tool → Component hierarchy

## Step 4: Tests First (TDD)
- tests/conftest.py — shared fixtures (mock env, app factory, test client, mock LLM)
- tests/test_api_endpoints.py — 12 test cases:
  1. test_health_check
  2. test_health_check_includes_version
  3. test_websocket_echo
  4. test_websocket_json_message
  5. test_cors_headers_present
  6. test_config_loads_models_json
  7. test_config_loads_dropdowns_json
  8. test_dropdowns_cascade
  9. test_llm_client_dispatches_to_openrouter
  10. test_llm_client_dispatches_to_openai
  11. test_llm_client_tracks_tokens
  12. test_llm_client_tracks_cost

## Step 5: Implementation
- backend/config.py — Settings loader (.env + json)
- backend/utils/llm_client.py — Provider-agnostic LLMClient + LLMResponse dataclass
- backend/utils/openrouter.py — OpenRouter HTTP client
- backend/utils/openai_client.py — OpenAI SDK client
- backend/main.py — FastAPI app with /health, /ws, /api/config/* endpoints

## Step 6: Verification
- pytest tests/test_api_endpoints.py — all pass
- uvicorn backend.main:app — server starts
- curl /health → 200 OK
- WebSocket echo functional

---

## Completion Criteria
- All 12 tests pass
- Server starts and responds to /health
- WebSocket echo works
- Config files load correctly
- CW15 xlsx present in data/raw/
