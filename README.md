# Engram — Multi-Agent Support System

Three AI agents (Analyzer, Finder, Reviewer) collaborate to diagnose technical issues,
search past cases, and validate solutions. Knowledge accumulates automatically as you
resolve cases — the system gets smarter the more you use it.

Built for field engineers, support teams, and anyone who solves recurring technical
problems and wants their solutions to become searchable institutional knowledge.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/engram.git
cd engram

# 2. Install (Python 3.12+ required)
python -m venv .venv
.venv/bin/pip install -e ".[dev]"    # Linux/Mac
# or: .venv\Scripts\pip install -e ".[dev]"  # Windows

# 3. Start
uvicorn backend.main:app --port 8000

# 4. Open http://localhost:8000
# 5. Go to Settings > API Keys > enter your OpenRouter key > Save
```

No `.env` editing required — API keys are set directly in the app.

## What It Does

```
You describe a problem
    → Analyzer diagnoses root causes (with probability %)
    → Finder searches past cases + manuals for evidence
    → Reviewer validates the solution against official procedures
    → Knowledge is saved for next time
```

Every resolved case becomes a searchable record. Next time a similar issue comes up,
the agents cite your past solutions. Your team's collective experience compounds.

## Architecture

```
Frontend (React + Vite)         → http://localhost:8000
    ↕ WebSocket
Backend (FastAPI + Python)      → Orchestrator → 3 Agents
    ↕                               ↕
ChromaDB (vector search)        SQLite (structured data)
    ↕
DB Builder (bulk import tool)   → Manuals, SOPs, documentation
```

- **Offline-first**: everything runs locally, no cloud dependency
- **LLM-agnostic**: works with any OpenRouter or OpenAI model
- **Knowledge grows**: cases accumulate as you work, no extra effort
- **Team sync**: optional mini-PC server syncs cases across team members

## DB Builder

Bulk-import your documentation (PDFs, Word, Excel, Markdown) into the knowledge base:

```bash
cd dbbuilder
pip install -e ".[dev]"
python -m db_builder --cli scan    # Find files
python -m db_builder --cli build   # Chunk → embed → ChromaDB
```

Or use the GUI: `python -m db_builder` (requires PySide6).

## Team Sync (Optional)

Share knowledge across team members with a mini-PC sync server:

```bash
# On the server (any PC on your LAN)
uvicorn sync_server.main:app --host 0.0.0.0 --port 9000

# On each team member's PC (.env)
SYNC_SERVER_URL=http://server-ip:9000
SYNC_DEVICE_NAME=My-PC
```

Dashboard at `http://server-ip:9000/sync/dashboard` shows team activity.

### Share Without a Server

```bash
# Export your knowledge
python -m backend.sync.export export --output engram-knowledge.zip

# Colleague imports
python -m backend.sync.export import --input engram-knowledge.zip
```

## Configuration

All settings are in the app UI: `http://localhost:8000/settings`

| Tab | What |
|-----|------|
| **Models** | Choose LLM model per agent role |
| **API Keys** | Enter + test + save API keys (persists to `.env`) |
| **VectorDB** | Knowledge base stats (cases, manuals, chunks) |
| **Dropdowns** | Customize the Account → Product → Module hierarchy |
| **Sync** | Team sync server status |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+N` | New chat |
| `Ctrl+K` | Focus input |
| `Ctrl+B` | Toggle sidebar |
| `Ctrl+,` | Settings |
| `Escape` | Stop agents |

## Tech Stack

- **Backend**: Python, FastAPI, ChromaDB, SQLite
- **Frontend**: React 19, TypeScript, Vite
- **LLM**: OpenRouter (Gemini Flash Lite default, configurable)
- **Embeddings**: OpenAI text-embedding-3-small via OpenRouter
- **Tests**: pytest (88) + vitest (7)

## License

MIT
