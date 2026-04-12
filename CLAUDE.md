# Engram — Multi-Agent Support System

## Project Overview
Engram is an open-source multi-agent AI support system for technical troubleshooting.
Three specialized agents (Analyzer, Finder, Reviewer) collaborate through an orchestrated discussion
to diagnose issues, find relevant past cases, and validate solutions against official procedures.

Designed for field engineers, support teams, and anyone who solves recurring technical problems
and wants their solutions to accumulate as searchable knowledge.

## Core Principles

1. **Test-Driven**: Tests are written BEFORE implementation code.
   Tests are the executable version of the spec. "If it's not tested, it's not implemented."

2. **No stubs**: Every file contains working code. No TODO comments, no placeholders,
   no "implement later". If a module isn't ready, it doesn't exist yet.

## Architecture Decisions

- **LLM Providers**: OpenRouter + OpenAI, configurable per agent role in `data/config/models.json`
- **Embeddings**: OpenRouter (`openai/text-embedding-3-small`, 1536 dims).
  Every collection (`case_records`, `traces`, `weekly`, `manuals`) is
  opened with `backend/knowledge/embedding_function.py::OpenRouterEmbeddingFunction`
  so the semantic space is consistent. Tests inject `FakeEmbeddingFunction` via conftest.
- **VectorDB**: ChromaDB (local file persistence in `data/chroma_db/`).
  The `manuals` collection is produced by the separate DB Builder app
  and read by Engram at query time.
- **Structured DB**: SQLite (`data/sqlite/engram.db`) for case metadata, cost tracking, audit
- **User scope**: Single-user, no authentication
- **Config**: `.env` for secrets, JSON files for application config
- **LLM abstraction**: `backend/utils/llm_client.py` — provider-agnostic with token/cost tracking

## Development Rules

- Python: pytest, async/await, type hints required
- Frontend: React + TypeScript + Vite + vitest (regression tests)
- Tests before implementation, always

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
│   └── graph.py            # NetworkX context graph
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
├── chroma_db/              # ChromaDB persistence (gitignored)
└── sqlite/                 # SQLite database (gitignored)

dbbuilder/                  # Separate PySide6 app for bulk document import
scripts/
├── bootstrap.py            # Initial bulk data ingest
└── dreaming_cron.py        # Nightly dreaming pipeline

tests/                      # pytest test suite
frontend/                   # React + TypeScript + Vite
```

## Key Policies

### Contribution Types
Agent responses must be one of:
- `NEW_EVIDENCE` — New data, source, or reasoning not yet in conversation
- `COUNTER` — Reasoned disagreement with another agent
- `ASK_STAKEHOLDER` — Request for info from user or another agent
- `REVISE` — Self-correction based on new information
- `PASS` — Nothing substantive to add (not disguised as contribution)

### VectorDB Chunk Types
- **Type A** (`case_record`): LLM-structured case summary on close
- **Type B** (`conversation_trace`): Raw conversation + tacit signals, never merged
- **Type C** (`weekly_report`): Parsed weekly report rows with issue threading

### Silo Key Format
`{account}_{tool}_{component}` — e.g., `ClientA_ProductA_Module1`

### Tacit Knowledge Extraction
On case close, LLM scans conversation for field-only knowledge:
field decisions, customer-specific conditions, unofficial interpretations,
tool-specific quirks, priority judgments.

## Commands

```bash
# Backend
pytest tests/ -v
uvicorn backend.main:app --port 8000

# Frontend
cd frontend && npm run dev      # Dev server :3000
cd frontend && npm run build    # Production build

# Scripts
python scripts/bootstrap.py --weekly data/raw/weekly_reports/example.xlsx
python scripts/dreaming_cron.py --export-graph data/graph.json
```
