# ZEMAS — ZEISS EUV Multi-Agent Support System

> **FIRST THING**: Read `docs/status.md` at the start of every new session to understand project state before doing anything else.

## Project Overview
ZEMAS is a multi-agent AI support system for ZEISS EUV lithography equipment (PROVE, AIMS).
Three specialized agents (Analyzer, Finder, Reviewer) collaborate through an orchestrated discussion
to diagnose equipment issues, find relevant past cases, and validate solutions against official procedures.

**Codename**: ZEMAS
**Author**: Kiwon (Application Engineer, ZEISS Korea)
**Master spec**: `docs/scaffolding-plan-v3.md` (single source of truth)

## Core Principles

1. **Spec-Driven**: `docs/scaffolding-plan-v3.md` is the single source of truth.
   All implementation follows its data structures, API contracts, and policies exactly.
   If spec and code diverge, update the spec first.

2. **Test-Driven**: Tests are written BEFORE implementation code.
   Tests are the executable version of the spec. "If it's not tested, it's not implemented."

3. **No stubs**: Every file contains working code. No TODO comments, no placeholders,
   no "implement later". If a module isn't ready, it doesn't exist yet.

## Architecture Decisions

- **LLM Providers**: OpenRouter + OpenAI, configurable per agent role in `data/config/models.json`
- **Cost-effective model**: `google/gemini-3.1-flash-lite-preview` via OpenRouter
- **Power model**: GPT-5.4 / Codex via OpenAI
- **Embeddings**: OpenRouter (`openai/text-embedding-3-small`, 1536 dims).
  Every collection (`case_records`, `traces`, `weekly`, `manuals`) is
  opened with `backend/knowledge/embedding_function.py::OpenRouterEmbeddingFunction`
  so the semantic space is consistent and cross-project (DB Builder)
  queries work. Tests inject `FakeEmbeddingFunction` via a conftest
  autouse fixture.
- **VectorDB**: ChromaDB (local file persistence in `data/chroma_db/`).
  The `manuals` collection is produced by the separate DB Builder app
  and read by ZEMAS — see `docs/status.md` "DB Builder Integration"
  for the compatibility contract.
- **Structured DB**: SQLite (`data/sqlite/zemas.db`) for case metadata, cost tracking, audit
- **User scope**: Single-user, no authentication
- **Config**: `.env` for secrets, JSON files for application config
- **LLM abstraction**: `backend/utils/llm_client.py` — provider-agnostic with token/cost tracking

## Development Rules

- Python: pytest, async/await, type hints required
- Frontend: React + TypeScript + Vite
- Tests before implementation, always
- Follow `docs/scaffolding-plan-v3.md` Section references exactly
- Each phase has explicit completion criteria — verify before moving on
- Errors in tests → fix immediately, never skip to next phase

## Current Status

**Read `docs/status.md` at the start of every session to understand project state and resume work.**

## Implementation Plans

- **Phase 12.1 + 0-A**: `docs/implementation-plan-phase0a.md` — Project skeleton, backend foundation (COMPLETE)

## Directory Structure

```
backend/                    # Python backend (FastAPI)
├── main.py                 # FastAPI app, CORS, WebSocket, API routes
├── config.py               # Settings loader (.env + JSON configs)
├── agents/                 # Multi-agent system
│   ├── base_agent.py       # Base LLM agent with contribution parsing
│   ├── orchestrator.py     # Collaborative loop, contribution validation
│   ├── analyzer.py         # Root cause analysis agent
│   ├── finder.py           # Knowledge search agent
│   └── reviewer.py         # Procedure validation agent
├── knowledge/              # Knowledge management
│   ├── vectordb.py         # ChromaDB wrapper + silo filtering
│   ├── recording_policy.py # Type A/B/C chunk builders
│   ├── tacit_extractor.py  # Tacit knowledge extraction from conversations
│   ├── weekly_ingester.py  # Excel weekly report parser (dual format)
│   ├── dreaming.py         # Light/REM/Deep sleep pipeline
│   ├── dedup.py            # Exact + semantic deduplication
│   ├── graph.py            # NetworkX context graph
│   └── graph_export.py     # Graph JSON export/import
├── memory/                 # Session & case memory
│   ├── case_recorder.py    # Auto-create Type A+B chunks on case close
│   └── preloader.py        # Session pre-loading (past cases into context)
└── utils/                  # Shared utilities
    ├── llm_client.py       # Provider-agnostic LLM client + cost tracking
    ├── openrouter.py       # OpenRouter API client
    └── openai_client.py    # OpenAI API client

data/
├── config/
│   ├── models.json         # Role → provider → model mapping
│   └── dropdowns.json      # Account → Tool → Component hierarchy
├── raw/weekly_reports/     # Source Excel files
├── chroma_db/              # ChromaDB persistence (gitignored)
└── sqlite/                 # SQLite database (gitignored)

scripts/
├── bootstrap.py            # Initial bulk data ingest
└── dreaming_cron.py        # Nightly dreaming pipeline

tests/                      # pytest test suite (TDD)
frontend/                   # React + TypeScript + Vite (Phase 0-C)
docs/                       # Specs and plans
```

## Key Policies

### Contribution Types (Section 3.1)
Agent responses must be one of:
- `NEW_EVIDENCE` — New data, source, or reasoning not yet in conversation
- `COUNTER` — Reasoned disagreement with another agent
- `ASK_STAKEHOLDER` — Request for info from user or another agent
- `REVISE` — Self-correction based on new information
- `PASS` — Nothing substantive to add (not disguised as contribution)

### VectorDB Chunk Types (Section 5.1)
- **Type A** (`case_record`): LLM-structured case summary on close
- **Type B** (`conversation_trace`): Raw conversation + tacit signals, never merged
- **Type C** (`weekly_report`): Parsed weekly report rows with issue threading

### Silo Key Format
`{account}_{tool}_{component}` — e.g., `SEC_PROVE_InCell`

### Tacit Knowledge Extraction (Section 5.1 delta)
On case close, LLM scans conversation for field-only knowledge:
field decisions, customer-specific conditions, unofficial interpretations,
tool-specific quirks, priority judgments.

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available skills: `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/connect-chrome`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/cso`, `/autoplan`, `/plan-devex-review`, `/devex-review`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`, `/learn`.
