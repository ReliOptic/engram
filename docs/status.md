# ZEMAS Project Status

**Last updated**: 2026-04-12
**Overall progress**: ALL PHASES COMPLETE (9/9) + UX OVERHAUL + DB BUILDER INTEGRATION + QA FIXES
**Total tests**: 79/79 backend + 7/7 frontend (vitest) + 130/130 DB Builder

---

## Phase Roadmap

| # | Phase | Description | Status | Tests |
|---|-------|------------|--------|-------|
| 12.1 | CLAUDE.md | Project constitution | COMPLETE | — |
| 0-A | Backend foundation | FastAPI, config, LLM clients, WebSocket | COMPLETE | 12/12 pass |
| 0-B | Orchestrator + Agents | Collaborative loop, contribution validation, 3 agents | COMPLETE | 11/11 pass |
| 1-A | VectorDB + Recording | ChromaDB wrapper, Type A/B/C chunks, silo filtering | COMPLETE | 12/12 pass |
| 0-C | Frontend shell | React 3-column UI, cascading dropdown, WebSocket | COMPLETE | build OK |
| 1-B | Tacit + Weekly Ingest | Tacit extractor, weekly report parser, bootstrap | COMPLETE | 10/10 pass |
| 1-C | Session Pre-loading | RAG context builder, Finder VectorDB integration | COMPLETE | 3/3 pass |
| 1-D | Frontend + Integration | Full frontend-backend connection, e2e test | COMPLETE | 2/2 pass |
| 2 | Dreaming | Light/REM/Deep sleep, dedup, graph, cron | COMPLETE | 3/3 pass |
| **UX** | **UX Overhaul** | **Session persistence, settings, resizable layout, polish** | **COMPLETE** | **14/14 pass** |
| **DBI** | **DB Builder Integration** | **Shared OpenRouter EF, manuals collection, cross-project contract** | **COMPLETE** | **7/7 pass** |
| **QA** | **QA Fixes + Frontend Tests** | **WS StrictMode, delete confirm, shortcuts, responsive, vitest** | **COMPLETE** | **7/7 frontend** |

---

## UX Overhaul — Completed 2026-04-10

### Backend Changes
- **Session persistence**: `sessions` + `messages` tables in SQLite, 8 new DB methods
- **Session API**: POST/GET/PATCH/DELETE `/api/sessions`, GET `/api/sessions/{id}` (with messages)
- **Settings API**: GET/PUT `/api/settings/models`, GET `/api/settings/vectordb/stats`, POST import, PUT dropdowns, POST test-connection
- **WebSocket upgrade**: auto-creates session on first message, persists all messages (user + agent) with `session_id`
- **Config isolation**: `backend.main` uses `_cfg.DATA_DIR`/`_cfg.CONFIG_DIR` for proper test monkeypatching

### Frontend Changes
- **react-router-dom**: `/` → ChatPage, `/settings` → SettingsPage
- **ChatPage** (`pages/ChatPage.tsx`): extracted from App.tsx, manages `currentSessionId`, loads sessions on click
- **SettingsPage** (`pages/SettingsPage.tsx`): 4 tabs — Models, API Keys, VectorDB, Dropdowns
- **ResizableLayout** (`components/ResizableLayout.tsx`): draggable dividers (mouse events), min/max widths, sidebar collapse (double-click), localStorage persistence
- **HistorySidebar** (rewritten): sessions grouped by date (Today/Yesterday/Last 7 Days/Older), search, rename (inline edit), delete, context menu
- **Header** (redesigned): gear icon → `/settings`, removed New Chat button (moved to sidebar)
- **Toast** (`components/Toast.tsx`): context-based notifications (success/error/info), auto-dismiss 3s
- **Skeleton** (`components/Skeleton.tsx`): shimmer loading animation
- **Settings components**: ModelSettings (inline edit table), APIKeySettings (masked + test), VectorDBSettings (stats + import), DropdownSettings (tree view + JSON editor)
- **Keyboard shortcuts** (`hooks/useKeyboardShortcuts.ts`): Ctrl+N (new chat), Ctrl+K (focus input), Ctrl+, (settings), Ctrl+B (toggle left sidebar), Escape (stop)
- **CSS polish** (`index.css`): smooth transitions, hover states, focus-visible accessibility, shimmer/slideIn animations

### New Tests (14)
- `tests/test_sessions_api.py` — 9 tests: create, list, get+messages, 404, rename, archive, delete, message persistence, status filter
- `tests/test_settings_api.py` — 5 tests: get models (redacted), update models, vectordb stats, update dropdowns, test-connection unknown provider

### Files Changed/Created

**Backend (4 files)**:
- `backend/knowledge/database.py` — +sessions/messages tables, +8 methods
- `backend/main.py` — +11 API endpoints, WS session auto-save
- `tests/test_sessions_api.py` — NEW
- `tests/test_settings_api.py` — NEW

**Frontend (18 files)**:
- `package.json` — +react-router-dom
- `src/main.tsx` — +BrowserRouter
- `src/App.tsx` — rewritten: Routes + ToastProvider
- `src/pages/ChatPage.tsx` — NEW
- `src/pages/SettingsPage.tsx` — NEW
- `src/components/ResizableLayout.tsx` — NEW
- `src/components/HistorySidebar.tsx` — rewritten
- `src/components/Header.tsx` — redesigned
- `src/components/Toast.tsx` — NEW
- `src/components/Skeleton.tsx` — NEW
- `src/components/settings/ModelSettings.tsx` — NEW
- `src/components/settings/APIKeySettings.tsx` — NEW
- `src/components/settings/VectorDBSettings.tsx` — NEW
- `src/components/settings/DropdownSettings.tsx` — NEW
- `src/hooks/useSessions.ts` — NEW
- `src/hooks/useKeyboardShortcuts.ts` — NEW
- `src/hooks/useWebSocket.ts` — unchanged (session_id via payload)
- `src/index.css` — +transitions, +hover, +focus, +animations

**Test infra**:
- `tests/conftest.py` — +monkeypatch `backend.config.DATA_DIR` for proper isolation

---

## DB Builder Integration — COMPLETE (2026-04-12)

**Status**: ✅ Integrated. DB Builder (separate Windows app at
`C:\Users\ReliQbit\Downloads\ZEMAS_DB_Builder`) writes `manuals` chunks
that ZEMAS queries in-place via the shared `data/chroma_db/` directory.

**Rationale**: 1GB PDF chunking+embedding은 수 시간 소요, 파싱 로직 복잡
(표/이미지/다국어), 반복 실험 필요 → 전용 PySide6 앱으로 분리.

### Architecture
```
ZEMAS_DB_Builder/            ← PySide6 Windows app, builds ChromaDB
└── src/db_builder/
    ├── pipeline.py          ← parse → chunk → enrich → embed → write
    ├── store/
    │   ├── chromadb_writer.py       ← writes to shared chroma_db/
    │   └── embedding_function.py    ← OpenRouterEmbeddingFunction (mirror)
    └── config.py            ← ZEMAS_DATA_DIR/CONFIG_DIR env overrides

ZZZ/                         ← ZEMAS backend + frontend
├── data/chroma_db/          ← SHARED: DB Builder writes, ZEMAS reads
├── data/sqlite/zemas.db     ← ZEMAS-only: cases, sessions, messages
└── backend/knowledge/
    ├── vectordb.py          ← opens shared chroma_db/, OpenRouter EF
    └── embedding_function.py ← OpenRouterEmbeddingFunction (authoritative)
```

### Collection contract
| Collection | Owner | Type | Write path |
|------------|-------|------|------------|
| `case_records` | ZEMAS | A (case summaries) | `case_recorder.py` on case close |
| `traces` | ZEMAS | B (raw conversation, never merge) | `case_recorder.py` on case close |
| `weekly` | ZEMAS | C (weekly report rows) | `weekly_ingester.py` Excel parser |
| `manuals` | **DB Builder** | D (PDF/SOP chunks) | DB Builder pipeline |

### Compatibility rules (verified, not just promised)
- **Embedding model**: `openai/text-embedding-3-small` via OpenRouter on
  both sides. Dimension = **1536**, hard-asserted by
  `tests/test_integration_cross_project.py::test_embedding_dim_consistency`.
- **Embedding function identity**: Both projects register
  `OpenRouterEmbeddingFunction` with static `name() ==
  "openrouter-text-embedding-3-small"`. ChromaDB uses this name to match
  the function across reopens — **if you fork the class in one project,
  you must keep the name identical in both**.
- **Metadata filter contract**: ZEMAS `preloader.build_context` filters
  manuals via `where={"tool_family": tool}`. DB Builder auto-detects
  `tool_family` from the file path (PROVE / AIMS / WLCD keywords) and
  stores it on every chunk.
- **chunk_id**: Deterministic. DB Builder format is
  `m-{file_hash[:6]}_{location}_{index:03d}` (see
  `chunking/base.py::generate_chunk_id`).

### Shared persist_dir convention
- DB Builder's `DBBuilderConfig.chromadb_dir` defaults to
  `$ZEMAS_DATA_DIR/chroma_db`, so setting `ZEMAS_DATA_DIR` in both
  `.env` files makes them point at the same directory.
- **CLI build**: `python -m db_builder --cli build` (parse → chunk → embed →
  ChromaDB). Use `--file <path>` for single file, `--source manual` for type
  filter. Full pipeline verified E2E with 14 chunks from synthetic PROVE manual.
- **Concurrency caveat**: ChromaDB uses SQLite with file locks. Do not
  run a DB Builder build while the ZEMAS backend is actively querying —
  stop ZEMAS, run the build, restart ZEMAS. A long-lived ZEMAS session
  can stay open for reads while DB Builder is idle.

### Known gotchas (fixed, documented for future me)
1. **Collection name**: DB Builder used to write `zemas_manuals`; ZEMAS
   reads `manuals`. Renamed to `manuals` on the DB Builder side.
2. **Embedding dim silent mismatch**: ZEMAS's `VectorDB.search` used to
   swallow every exception, which hid a dimension mismatch between
   ChromaDB's default 384-dim ONNX MiniLM (when no EF is registered) and
   DB Builder's 1536-dim OpenRouter vectors. Both sides now attach the
   same `OpenRouterEmbeddingFunction`, and the `except` in
   `VectorDB.search` was narrowed so errors surface instead of returning
   `[]`.
3. **QThread signal override**: DB Builder's `ImportWorker.finished`
   used to shadow `QThread.finished`, which broke the DB-registration
   callback after file imports. Renamed to `import_done` (and
   `scan_done` for `ScanWorker`).

---

## Completed Work

### Phase 0-A — Backend Foundation
```
backend/main.py              — FastAPI app: /health, /ws (agent chat), /api/config/*
backend/config.py            — Settings loader (.env + models.json + dropdowns.json)
backend/utils/llm_client.py  — Provider-agnostic LLMClient + LLMResponse + cost tracking
backend/utils/openrouter.py  — OpenRouter HTTP client (Gemini Flash Lite, etc.)
backend/utils/openai_client.py — OpenAI SDK client (GPT-5.4, Codex)
data/config/models.json      — Role → provider → model mapping (7 roles)
data/config/dropdowns.json   — Account → Tool → Component (SEC, TSMC, Intel, SKH)
tests/conftest.py            — Shared fixtures (mock env, app factory, test client)
tests/test_api_endpoints.py  — 12 test cases, all passing
```

### Phase 0-B — Orchestrator + Agents
```
backend/agents/base_agent.py    — BaseAgent: LLM call + JSON response parsing + fallback
backend/agents/orchestrator.py  — Orchestrator loop, AgentResponse, OrchestratorResult,
                                  CONTRIBUTION_TYPES, validate_contribution(),
                                  rubber-stamp detection, @mention routing, MAX_ROUNDS=15
backend/agents/analyzer.py      — Root cause analysis agent (PROVE/AIMS diagnostics)
backend/agents/finder.py        — Knowledge search agent (VectorDB + case cross-reference)
backend/agents/reviewer.py      — Procedure validation agent (manual compliance check)
tests/test_orchestrator.py      — 6 tests: min-contribution, rubber-stamp, @mention,
                                  ask-user, max-rounds, all-pass termination
tests/test_contribution_validator.py — 5 tests: new evidence, repetition, counter,
                                       bare agreement, revision
```

### Phase 1-A — VectorDB + Recording Policy
```
backend/knowledge/vectordb.py       — ChromaDB wrapper: PersistentClient, collection management,
                                      silo-based filtering (search_by_silo), similarity search
backend/knowledge/recording_policy.py — build_type_a_chunk (case_record), build_type_b_chunk
                                        (conversation_trace), build_type_c_chunk (weekly_report),
                                        silo key builder, issue thread ID, component inference
backend/memory/case_recorder.py      — CaseRecorder: case close → Type A + Type B auto-creation
backend/knowledge/database.py       — SQLite: cases, cost_log, sessions, messages tables
data/config/agents/common.md         — Shared contribution format rules
data/config/agents/analyzer.md       — Analyzer prompt + metadata (YAML frontmatter)
data/config/agents/finder.md         — Finder prompt + metadata
data/config/agents/reviewer.md       — Reviewer prompt + metadata
tests/test_vectordb_recording.py     — 6 tests: Type A/B/C creation, silo key, weekly threading
tests/test_database.py              — 6 tests: create/close case, filter, cost logging
```

### Phase 0-C — Frontend Shell
```
frontend/                           — Vite + React 19 + TypeScript 6 project
frontend/vite.config.ts             — Dev server port 3000, proxy /api→8000, /ws→ws://8000
frontend/src/index.css              — ZEISS Design System CSS variables (#141E8C, Space Grotesk)
frontend/src/types/index.ts         — TypeScript types (AgentMessage, SiloSelection, etc.)
frontend/src/components/Header.tsx   — ZEISS blue header, WebSocket status + gear icon
frontend/src/components/Layout.tsx   — 3-column grid layout (kept for SettingsPage)
frontend/src/components/ResizableLayout.tsx — Draggable dividers + sidebar collapse
frontend/src/components/AgentPanel.tsx — Agent cards with real-time status badges
frontend/src/components/ChatTimeline.tsx — Messages with @mention highlighting
frontend/src/components/ChatInput.tsx    — Cascading dropdown + text input + file upload
frontend/src/components/SourceSidebar.tsx — Source document references
frontend/src/components/HistorySidebar.tsx — Session history with date groups, search, rename
frontend/src/components/Toast.tsx    — Toast notification system
frontend/src/components/Skeleton.tsx — Shimmer loading skeleton
frontend/src/components/settings/*   — ModelSettings, APIKeySettings, VectorDBSettings, DropdownSettings
frontend/src/pages/ChatPage.tsx      — Main chat page with session management
frontend/src/pages/SettingsPage.tsx   — 4-tab settings page
frontend/src/hooks/useWebSocket.ts   — WebSocket hook with auto-reconnect
frontend/src/hooks/useSessions.ts    — Session CRUD hook
frontend/src/hooks/useKeyboardShortcuts.ts — Keyboard shortcuts
frontend/src/App.tsx                 — Routes: / → ChatPage, /settings → SettingsPage
```

### Phase 1-B — Tacit Extraction + Weekly Ingestion
```
backend/knowledge/tacit_extractor.py   — TACIT_EXTRACTION_PROMPT (Korean/English),
                                         TacitExtractor.extract() → LLM → signal list,
                                         extract_and_store() → Type B metadata update
                                         Signal types: field_decision, customer_specific,
                                         unofficial_interpretation, tool_specific, priority_judgment
backend/knowledge/weekly_ingester.py   — WeeklyIngester: Excel parser for CW reports
                                         Auto-detects new format (CW09+) vs old format (CW52~CW08)
                                         parse_sheet(), parse_all_sheets()
scripts/bootstrap.py                   — CLI: --weekly, --all, --persist-dir
                                         Bulk ingest weekly reports → Type C chunks
tests/test_tacit_extractor.py          — 5 tests: field_decision, standard proc, greetings,
                                         empty, customer_specific
tests/test_weekly_ingester.py          — 5 tests: new format, old format, all sheets,
                                         diff detection, upsert dedup
```

### Phase 1-C — Session Pre-loading
```
backend/memory/preloader.py            — SessionPreloader + SessionContext
                                         build_context(): silo cases (10) + cross-silo (5) + weekly (5)
                                         to_prompt_text(): formatted for agent system prompt injection
                                         Max context: 40K chars (well under 256K token limit)
tests/test_session_preloader.py        — 3 tests: same-tool, cross-silo, context size
```

### Phase 1-D — Frontend + Integration
```
backend/main.py (updated)              — /ws upgraded from echo to real agent orchestrator
                                         WebSocket protocol: user_message → status_update → agent_message
                                         Streaming: thinking/done status per agent, final complete
                                         Fallback: echo mode when no API keys configured
                                         Session auto-creation + message persistence
tests/test_integration.py              — 2 tests: full case lifecycle (query → orchestrator →
                                         case close → VectorDB → pre-load next session),
                                         weekly report cross-reference
```

### Phase 2 — Dreaming
```
backend/knowledge/dedup.py             — DedupEngine + DedupReport
                                         Light Sleep: exact dedup (upsert), near-duplicate detection
                                         (cosine similarity > 0.92), trace protection (never merge)
backend/knowledge/graph.py             — KnowledgeGraph, GraphNode, GraphEdge
                                         build_from_vectordb(): nodes from chunks, edges from
                                         silo_key grouping and issue_thread_id linking
                                         to_dict() / from_dict(): JSON export/import
backend/knowledge/dreaming.py          — DreamingPipeline + DreamingReport
                                         Light Sleep: dedup all collections
                                         REM Sleep: pattern detection from tacit_signals (3+ → promote)
                                         Deep Sleep: graph consolidation from VectorDB
                                         export_graph() / import_graph() with conflict detection
scripts/dreaming_cron.py               — CLI: --persist-dir, --export-graph
                                         Nightly job for Windows Task Scheduler
tests/test_dedup.py                    — 3 tests: exact duplicate, semantic near-duplicate,
                                         trace never merged
```

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (React + Vite + react-router)        │
│  ResizableLayout → AgentPanel + History | Chat | Sources        │
│  SettingsPage → Models | API Keys | VectorDB | Dropdowns        │
│                   ↕ WebSocket (session-aware) ↕                 │
├─────────────────────────────────────────────────────────────────┤
│                    Backend (FastAPI)                             │
│  Orchestrator → Analyzer, Finder, Reviewer (round-robin)        │
│  Session Preloader → RAG context injection                      │
│  Case Recorder → dual-write ChromaDB + SQLite                   │
│  Tacit Extractor → LLM → tacit signal extraction                │
│  Session/Settings APIs → CRUD, config management                │
├─────────────────────────────────────────────────────────────────┤
│                    Knowledge Layer                               │
│  ChromaDB: case_records, traces, weekly, manuals                │
│  SQLite: cases, cost_log, sessions, messages                    │
│  Knowledge Graph: nodes + edges (silo, thread links)            │
├─────────────────────────────────────────────────────────────────┤
│                    Dreaming Pipeline (nightly)                   │
│  Light Sleep (dedup) → REM Sleep (patterns) → Deep Sleep (graph)│
└─────────────────────────────────────────────────────────────────┘
```

### Key patterns
- Config loaded eagerly in `create_app()` (not lifespan)
- `ZEMAS_CONFIG_DIR` env override for test isolation
- `_cfg.DATA_DIR` / `_cfg.CONFIG_DIR` used in main.py (monkeypatch-friendly)
- `LLMClient.complete(role, messages)` dispatches to correct provider
- Orchestrator testable via `_get_agent_response` override
- Repetition detection: Jaccard similarity (threshold 0.7)
- Tacit prompt: `.replace()` not `.format()` (JSON braces conflict)
- Weekly ingester: auto-detects new vs old format by column names
- Dedup: Type B traces NEVER merged (never_merge metadata flag)
- Graph: JSON export/import with conflict detection
- Sessions: auto-created on first WS message, messages persisted bidirectionally

### Commands
```bash
# Backend
cd /home/reliqbit/project/ZZZ
source .venv/bin/activate
pytest tests/ -v                              # 67 tests
uvicorn backend.main:app --reload             # Dev server :8000

# Frontend
cd frontend && npm run dev                    # Dev server :3000
source ~/.nvm/nvm.sh && node node_modules/typescript/bin/tsc -b && node node_modules/vite/bin/vite.js build  # Production build

# Scripts
python scripts/bootstrap.py --weekly data/raw/weekly_reports/CW15_Weekly_Apps.xlsx
python scripts/dreaming_cron.py --export-graph data/graph.json
```
