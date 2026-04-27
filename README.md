# Engram — Multi-Agent Support System

Three AI agents (Analyzer, Finder, Reviewer) collaborate to diagnose technical issues,
search past cases, and validate solutions. Knowledge accumulates automatically as you
resolve cases — the system gets smarter the more you use it.

Built for field engineers, support teams, and anyone who solves recurring technical
problems and wants their solutions to become searchable institutional knowledge.

## Quick Start

Already comfortable with Python and Node? Three commands and you're running:

```bash
git clone https://github.com/ReliOptic/engram.git && cd engram
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..
uvicorn backend.main:app --port 8000
# Open http://localhost:8000 → Settings → API Keys → paste OpenRouter key → Save
```

Otherwise, follow the full [Installation](#installation) and [Usage Guide](#usage-guide)
sections below.

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

## Installation

### Prerequisites

| Requirement | Version | Why |
|---|---|---|
| Python | 3.11 or newer | Backend runtime (FastAPI + ChromaDB) |
| Node.js | 20 or newer | Build the React frontend (one-time) |
| Git | any recent | Clone the repository |
| OpenRouter API key | — | Powers the agents — sign up at [openrouter.ai](https://openrouter.ai) |

> Windows users who don't want to install Python/Node can skip ahead to
> [Windows installer](#windows-installation) and download a prebuilt EXE.

### Step 1 — Get the code

```bash
git clone https://github.com/ReliOptic/engram.git
cd engram
```

### Step 2 — Install the backend

Create a virtual environment and install Engram into it:

```bash
# Linux / macOS
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

This pulls in FastAPI, ChromaDB, the OpenAI/OpenRouter clients, and the test runner.

### Step 3 — Build the frontend (once)

The backend serves the prebuilt React bundle from `frontend/dist/`. You need to
build it once before the first run (and again whenever you `git pull` and the
frontend changed):

```bash
cd frontend
npm install
npm run build
cd ..
```

If you're going to **develop** the UI, skip the build and run the Vite dev
server in a second terminal — see [Development mode](#development-mode) below.

### Step 4 — Start the server

```bash
uvicorn backend.main:app --port 8000
```

Open <http://localhost:8000> in your browser. You should see the Engram chat UI.

### Step 5 — Add your API key

1. Click the gear icon (top right) or press `Ctrl+,`.
2. Open the **API Keys** tab.
3. Paste your OpenRouter key, click **Test** to verify, then **Save**.

The key is written to a local `.env` file — no data leaves your machine except
calls to the LLM provider you configured.

## Usage Guide

### Your first chat

1. **Pick a context.** At the bottom of the chat, choose **Account → Tool →
   Component** from the cascading dropdowns. This "silo" decides which past
   cases and manuals the agents will search. (You can customise the dropdown
   tree in **Settings → Dropdowns**.)
2. **Describe your issue.** Type a short, factual description in the input
   box and press `Enter`. Example:
   > *"PRV-4412 alarm, 3nm offset on Module 1 reads after PM. Reproducible
   > on every wafer."*
3. **Watch the agents work.** They take turns:
   - **Analyzer** proposes weighted root causes.
   - **Finder** searches past cases, weekly reports, and manuals for evidence.
   - **Reviewer** maps applicable procedures from your manuals and challenges
     anything that doesn't fit.
   They will sometimes `@mention` each other or ask **you** for missing
   information — the conversation pauses until you reply.
4. **Apply the resolution.** When the discussion converges, the right-hand
   panel lists every source the agents cited (manuals, prior cases, weekly
   threads). Click any source to see what they're referring to.
5. **Close the case.** When the issue is resolved, click **Close case** and
   add a one-line resolution. Engram automatically:
   - Stores a structured summary (Type A) for similarity search,
   - Keeps the raw conversation (Type B) for tacit-knowledge mining,
   - Indexes both in ChromaDB and SQLite so the next session can find them.

### Bring in your manuals

Engram is most useful when it can search **your** documentation. Use the
DB Builder to bulk-import PDFs, Word docs, Excel sheets, and Markdown:

```bash
cd dbbuilder
pip install -e ".[dev]"
python -m db_builder           # GUI (requires PySide6)
# or
python -m db_builder --cli scan
python -m db_builder --cli build
```

Imported documents land in the same ChromaDB instance the agents query, so
they show up in Finder/Reviewer results immediately on the next chat.

### Import weekly reports

If your team keeps weekly issue reports in Excel, point Engram at them so the
Finder can stitch issue threads across weeks:

```bash
python scripts/bootstrap.py --weekly path/to/your-weekly-report.xlsx
```

### Day-to-day workflow

| When | Do this |
|---|---|
| New chat | `Ctrl+N` |
| Search past chats | Use the search box in the left sidebar |
| Settings | `Ctrl+,` (gear icon) |
| Stop the agents mid-discussion | `Escape` or **Stop** button |
| Give a chat a name | Right-click it in the sidebar → Rename |
| Export your knowledge | `python -m backend.sync.export export --output knowledge.zip` |

### Development mode

If you're modifying the frontend, run the Vite dev server in parallel for
hot reload:

```bash
# Terminal 1 — backend
uvicorn backend.main:app --port 8000 --reload

# Terminal 2 — frontend
cd frontend
npm run dev
# Open http://localhost:3000 (Vite proxies /api and /ws to :8000)
```

### Running the tests

```bash
pytest tests/ -q                  # backend (175 tests)
cd frontend && npm test           # frontend (91 tests)
```

### Troubleshooting

| Symptom | Fix |
|---|---|
| Browser shows raw JSON / 404 at `/` | The frontend isn't built — run `cd frontend && npm install && npm run build`. |
| "No matching cases" no matter what you ask | Knowledge base is empty. Import some manuals via DB Builder, or close a few cases first. |
| Agents reply with "echo mode" placeholders | API key not configured. Open Settings → API Keys, paste, Test, Save. |
| `ImportError: chromadb` after `git pull` | Dependencies changed. Re-run `pip install -e ".[dev]"`. |
| Port 8000 already in use | Pick another port: `uvicorn backend.main:app --port 8001`. |

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

## Windows Installation

### Option A: Download Installer (Recommended)

Download `Engram-Setup-x.x.x.exe` from [Releases](https://github.com/ReliOptic/engram/releases) and run it.
Choose components during install:

- **Engram** — main web app (opens in browser)
- **Engram DB Builder** — desktop GUI for bulk document import

### Option B: Build from Source

Requires Python 3.12+ and [Inno Setup 6](https://jrsoftware.org/isinfo.php) (for installer).

```batch
:: 1. Build both EXEs with PyInstaller
scripts\build_windows.bat

:: 2. (Optional) Create installer EXE
::    Open scripts\engram-setup.iss in Inno Setup Compiler → Build
::    Output: dist\Engram-Setup-0.1.0.exe
```

Without the installer, run directly:
- `dist\engram\engram.exe` — starts server + opens browser at http://localhost:8000
- `dist\engram-db-builder\engram-db-builder.exe` — launches DB Builder GUI

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
- **Tests**: pytest (175) + vitest (91)

## License

Apache License 2.0 — see [LICENSE](LICENSE)
