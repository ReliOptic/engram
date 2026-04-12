"""ZEMAS FastAPI application.

Entry point for the backend server. Provides:
- /health endpoint
- /ws WebSocket for agent chat (with session persistence)
- /api/config/* endpoints for frontend config loading
- /api/cases/* endpoints for case management
- /api/sessions/* endpoints for session/message persistence
- /api/settings/* endpoints for admin configuration
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import logging

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import VERSION, load_dropdowns_config, load_models_config
import backend.config as _cfg

logger = logging.getLogger(__name__)


async def _safe_send(websocket: WebSocket, data: dict) -> bool:
    """Send JSON over WebSocket, returning False if the socket is dead.

    React StrictMode double-mounts the frontend WebSocket hook. The first
    connection gets cleaned up, but the backend may still try to send on it.
    Without this guard, ``send_text`` raises ``WebSocketDisconnect`` or
    ``RuntimeError('Cannot call send once a close message has been sent')``,
    which crashes the entire handler and prevents session persistence.
    """
    try:
        await websocket.send_text(json.dumps(data))
        return True
    except (WebSocketDisconnect, RuntimeError) as e:
        logger.warning("WebSocket send failed (client likely disconnected): %s", e)
        return False


# --- Request models ---

class SessionCreate(BaseModel):
    title: str = ""
    silo_account: str = ""
    silo_tool: str = ""
    silo_component: str = ""

class SessionUpdate(BaseModel):
    title: str | None = None
    status: str | None = None

class TestConnectionRequest(BaseModel):
    provider: str
    api_key: str


def _get_db():
    """Get a shared ZemasDB instance."""
    from backend.knowledge.database import ZemasDB
    db_path = _cfg.DATA_DIR / "sqlite" / "zemas.db"
    return ZemasDB(str(db_path))


def create_app() -> FastAPI:
    """Factory function for creating the FastAPI app."""
    app = FastAPI(
        title="ZEMAS",
        description="ZEISS EUV Multi-Agent Support System",
        version=VERSION,
    )

    # Load config eagerly so it's available immediately (works with test clients too)
    app.state.models_config = load_models_config()
    app.state.dropdowns_config = load_dropdowns_config()

    # CORS — allow all origins in development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": VERSION}

    @app.get("/api/sync/status")
    async def sync_status():
        """Return current sync status for frontend header badge."""
        from backend.config import SYNC_SERVER_URL, SYNC_DEVICE_NAME
        if not SYNC_SERVER_URL:
            return {"enabled": False, "status": "disabled", "pending_events": 0}
        try:
            from backend.knowledge.database import ZemasDB
            db = ZemasDB(str(Path(_cfg.DATA_DIR) / "sqlite" / "zemas.db"))
            from backend.sync.queue import SyncQueue
            queue = SyncQueue(db.conn)
            from backend.sync.client import SyncClient
            client = SyncClient(SYNC_SERVER_URL, queue, SYNC_DEVICE_NAME)
            status = client.get_status()
            db.close()
            return status
        except Exception:
            return {"enabled": True, "status": "offline", "pending_events": 0}

    @app.get("/api/config/models")
    async def get_models_config():
        """Return model registry (API keys redacted)."""
        config = app.state.models_config
        safe_config = {
            "providers": {
                name: {"base_url": p["base_url"]}
                for name, p in config["providers"].items()
            },
            "roles": config["roles"],
            "cost_per_million_tokens": config.get("cost_per_million_tokens", {}),
        }
        return safe_config

    @app.get("/api/config/dropdowns")
    async def get_dropdowns_config():
        """Return account → tool → component hierarchy."""
        return app.state.dropdowns_config

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for agent chat.

        Protocol:
        - Client sends: {"type": "user_message", "payload": {"text": "...", "silo": {...}, "session_id": "..."}}
        - Server sends: {"type": "agent_message", "payload": {"agent": "...", "content": "...", "session_id": "...", ...}}
        - Server sends: {"type": "status_update", "payload": {"agent": "...", "status": "thinking"}}
        - Server sends: {"type": "error", "payload": {"message": "..."}}
        """
        await websocket.accept()
        try:
            while True:
                raw = await websocket.receive_text()

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    msg = {"type": "user_message", "payload": {"text": raw}}

                if msg.get("type") == "user_message":
                    payload = msg.get("payload", {})
                    text = payload.get("text", str(raw))
                    silo = payload.get("silo", {})
                    session_id = payload.get("session_id", "")

                    # Auto-create session on first message if no session_id
                    db = _get_db()
                    try:
                        if not session_id:
                            session_id = db.create_session(
                                title=text[:80],
                                silo_account=silo.get("account", ""),
                                silo_tool=silo.get("tool", ""),
                                silo_component=silo.get("component", ""),
                            )

                        # Persist user message
                        db.add_message(
                            session_id=session_id,
                            agent="user",
                            content=text,
                            silo_account=silo.get("account", ""),
                            silo_tool=silo.get("tool", ""),
                            silo_component=silo.get("component", ""),
                        )
                    finally:
                        db.close()

                    # Send acknowledgment with session_id
                    if not await _safe_send(websocket, {
                        "type": "status_update",
                        "payload": {
                            "status": "processing",
                            "session_id": session_id,
                            "case_id": f"{silo.get('account', 'X')}-{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}",
                        },
                    }):
                        continue  # Client gone, skip processing

                    # Run orchestrator (if LLM configured), otherwise echo
                    try:
                        await _run_orchestrator(
                            app, websocket, text, silo, session_id,
                        )
                    except Exception as e:
                        await _safe_send(websocket, {
                            "type": "error",
                            "payload": {"message": str(e)},
                        })
                else:
                    # Echo for non-message types (backward compat)
                    try:
                        await websocket.send_text(raw)
                    except (WebSocketDisconnect, RuntimeError):
                        pass

        except WebSocketDisconnect:
            pass

    # --- Cases API ---

    @app.get("/api/cases")
    async def list_cases(
        account: str | None = None,
        tool: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ):
        """List cases from SQLite with optional filters."""
        from backend.knowledge.database import ZemasDB
        db_path = _cfg.DATA_DIR / "sqlite" / "zemas.db"
        if not db_path.exists():
            return []
        db = ZemasDB(str(db_path))
        try:
            return db.list_cases(account=account, tool=tool, status=status, limit=limit)
        finally:
            db.close()

    # --- Sessions API ---

    @app.post("/api/sessions")
    async def create_session(body: SessionCreate):
        db = _get_db()
        try:
            session_id = db.create_session(
                title=body.title,
                silo_account=body.silo_account,
                silo_tool=body.silo_tool,
                silo_component=body.silo_component,
            )
            session = db.get_session(session_id)
            return session
        finally:
            db.close()

    @app.get("/api/sessions")
    async def list_sessions(status: str | None = None, limit: int = 50):
        db = _get_db()
        try:
            return db.list_sessions(status=status, limit=limit)
        finally:
            db.close()

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        db = _get_db()
        try:
            session = db.get_session(session_id)
            if not session:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=404, content={"detail": "Session not found"})
            messages = db.get_messages(session_id)
            return {**session, "messages": messages}
        finally:
            db.close()

    @app.patch("/api/sessions/{session_id}")
    async def update_session(session_id: str, body: SessionUpdate):
        db = _get_db()
        try:
            session = db.get_session(session_id)
            if not session:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=404, content={"detail": "Session not found"})
            if body.title is not None:
                db.update_session_title(session_id, body.title)
            if body.status == "archived":
                db.archive_session(session_id)
            return db.get_session(session_id)
        finally:
            db.close()

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str):
        db = _get_db()
        try:
            session = db.get_session(session_id)
            if not session:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=404, content={"detail": "Session not found"})
            db.delete_session(session_id)
            return {"ok": True}
        finally:
            db.close()

    # --- Settings API ---

    @app.get("/api/settings/models")
    async def get_settings_models():
        """Get models.json config (keys redacted)."""
        config = app.state.models_config
        safe = {
            "providers": {
                name: {"base_url": p["base_url"]}
                for name, p in config["providers"].items()
            },
            "roles": config["roles"],
            "cost_per_million_tokens": config.get("cost_per_million_tokens", {}),
        }
        return safe

    @app.put("/api/settings/models")
    async def update_settings_models(body: dict):
        """Update model assignments per role."""
        config = app.state.models_config
        if "roles" in body:
            config["roles"] = body["roles"]
        models_path = _cfg.CONFIG_DIR / "models.json"
        with open(models_path, "w") as f:
            json.dump(config, f, indent=2)
        app.state.models_config = config
        return {"ok": True}

    @app.get("/api/settings/vectordb/stats")
    async def get_vectordb_stats():
        """Get collection counts from ChromaDB."""
        from backend.knowledge.vectordb import VectorDB, COLLECTIONS
        persist_dir = str(_cfg.DATA_DIR / "chroma_db")
        try:
            vdb = VectorDB(persist_dir=persist_dir)
            stats = {}
            for name in COLLECTIONS:
                try:
                    stats[name] = vdb.count(name)
                except Exception:
                    stats[name] = 0
            return stats
        except Exception:
            return {name: 0 for name in COLLECTIONS}

    @app.post("/api/settings/vectordb/import")
    async def import_vectordb(file: UploadFile = File(...)):
        """Import external ChromaDB archive (zip/tar)."""
        import shutil
        import tempfile

        content = await file.read()
        persist_dir = _cfg.DATA_DIR / "chroma_db"

        with tempfile.NamedTemporaryFile(suffix=file.filename, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            extract_dir = Path(tempfile.mkdtemp())
            if file.filename and file.filename.endswith(".zip"):
                import zipfile
                with zipfile.ZipFile(tmp_path) as zf:
                    zf.extractall(extract_dir)
            elif file.filename and (file.filename.endswith(".tar") or file.filename.endswith(".tar.gz") or file.filename.endswith(".tgz")):
                import tarfile
                with tarfile.open(tmp_path) as tf:
                    tf.extractall(extract_dir)
            else:
                return {"ok": False, "error": "Unsupported format. Use .zip or .tar/.tar.gz"}

            # Find the chroma_db directory in the extracted content
            # It could be at root or nested one level
            source = extract_dir
            for child in extract_dir.iterdir():
                if child.is_dir() and child.name in ("chroma_db", "data"):
                    source = child
                    break

            # Copy into persist_dir
            if persist_dir.exists():
                shutil.rmtree(persist_dir)
            shutil.copytree(source, persist_dir)

            return {"ok": True, "message": f"Imported from {file.filename}"}
        finally:
            tmp_path.unlink(missing_ok=True)

    @app.put("/api/settings/dropdowns")
    async def update_dropdowns(body: dict):
        """Update dropdowns.json."""
        dropdowns_path = _cfg.CONFIG_DIR / "dropdowns.json"
        with open(dropdowns_path, "w") as f:
            json.dump(body, f, indent=2)
        app.state.dropdowns_config = body
        return {"ok": True}

    @app.post("/api/settings/test-connection")
    async def test_connection(body: TestConnectionRequest):
        """Test API key validity against a provider."""
        import httpx
        provider = body.provider
        api_key = body.api_key

        if provider == "openrouter":
            url = "https://openrouter.ai/api/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        elif provider == "openai":
            url = "https://api.openai.com/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        else:
            return {"ok": False, "error": f"Unknown provider: {provider}"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return {"ok": True, "provider": provider}
                else:
                    return {"ok": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # --- File Upload ---

    @app.post("/api/upload")
    async def upload_file(file: UploadFile = File(...)):
        """Upload a file for agent reference.

        Saves to data/uploads/ and returns the file path.
        """
        upload_dir = Path("data/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        safe_name = f"{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}_{file.filename}"
        dest = upload_dir / safe_name

        content = await file.read()
        dest.write_bytes(content)

        return {
            "filename": file.filename,
            "saved_as": str(dest),
            "size_bytes": len(content),
        }

    # --- Knowledge API ---

    @app.get("/api/knowledge/stats")
    async def get_knowledge_stats():
        """Comprehensive knowledge base statistics for the dashboard.

        Returns collection counts, case history, and source breakdown.
        """
        from backend.knowledge.vectordb import VectorDB, COLLECTIONS
        persist_dir = str(_cfg.DATA_DIR / "chroma_db")

        result = {
            "collections": {},
            "total_chunks": 0,
            "cases": {"total": 0, "recent_7d": 0},
            "sources": [],
        }

        try:
            vdb = VectorDB(persist_dir=persist_dir)
            for name in COLLECTIONS:
                try:
                    count = vdb.count(name)
                except Exception:
                    count = 0
                result["collections"][name] = count
                result["total_chunks"] += count
        except Exception:
            result["collections"] = {name: 0 for name in COLLECTIONS}

        # Case stats from SQLite
        db = _get_db()
        try:
            row = db._conn.execute("SELECT COUNT(*) FROM cases").fetchone()
            result["cases"]["total"] = row[0] if row else 0

            row = db._conn.execute(
                "SELECT COUNT(*) FROM cases WHERE created_at > datetime('now', '-7 days')"
            ).fetchone()
            result["cases"]["recent_7d"] = row[0] if row else 0

            # Session count
            row = db._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
            result["sessions_total"] = row[0] if row else 0
        except Exception:
            pass
        finally:
            db.close()

        return result

    @app.get("/api/knowledge/search")
    async def search_knowledge(
        q: str,
        tool: str = "",
        collection: str = "manuals",
        n: int = 10,
    ):
        """Search the knowledge base directly. For manual/case/weekly lookup."""
        from backend.knowledge.vectordb import VectorDB
        persist_dir = str(_cfg.DATA_DIR / "chroma_db")

        try:
            vdb = VectorDB(persist_dir=persist_dir)
            where = {"tool_family": tool} if tool else None
            results = vdb.search(collection, q, n_results=n, where=where)
            return {"results": results, "count": len(results)}
        except Exception as e:
            return {"results": [], "count": 0, "error": str(e)}

    # Serve frontend dist/ if it exists (production mode — no Node.js needed)
    dist_dir = Path(__file__).parent.parent / "frontend" / "dist"
    if dist_dir.exists():
        from starlette.responses import FileResponse

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            """Serve pre-built frontend. SPA catch-all for client-side routes."""
            file_path = dist_dir / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(dist_dir / "index.html"))

    return app


async def _run_orchestrator(app, websocket: WebSocket, query: str, silo: dict, session_id: str = ""):
    """Run the multi-agent orchestrator, streaming updates to WebSocket.

    If LLM client is not configured (no API keys), falls back to echo mode.
    """
    from backend.agents.orchestrator import Orchestrator, AgentResponse
    from backend.agents.analyzer import AnalyzerAgent
    from backend.agents.finder import FinderAgent
    from backend.agents.reviewer import ReviewerAgent
    from backend.utils.llm_client import LLMClient

    try:
        llm = LLMClient(app.state.models_config)
    except Exception:
        # No API keys — echo mode fallback
        msg_id = str(uuid.uuid4())
        await _safe_send(websocket, {
            "type": "agent_message",
            "payload": {
                "id": msg_id,
                "agent": "system",
                "content": f"Echo: {query}",
                "contributionType": "",
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "session_id": session_id,
            },
        })
        # Persist echo message
        if session_id:
            db = _get_db()
            try:
                db.add_message(session_id=session_id, agent="system", content=f"Echo: {query}")
            finally:
                db.close()
        return

    # Pre-load relevant context from knowledge base
    from backend.memory.preloader import SessionPreloader
    from backend.knowledge.vectordb import VectorDB

    context_text = ""
    try:
        vdb = VectorDB(persist_dir=str(Path(_cfg.DATA_DIR) / "chroma_db"))
        preloader = SessionPreloader(vdb)
        ctx = await preloader.build_context(
            account=silo.get("account", ""),
            tool=silo.get("tool", ""),
            component=silo.get("component", ""),
            query=query,
        )
        context_text = ctx.to_prompt_text()
    except Exception:
        pass  # No context available yet — first run or empty DB

    # Inject context into query if available
    augmented_query = query
    if context_text:
        augmented_query = (
            f"{query}\n\n"
            f"--- Knowledge Base Context ---\n{context_text}"
        )

    orchestrator = Orchestrator(llm)
    orchestrator.register_agent("analyzer", AnalyzerAgent(llm))
    orchestrator.register_agent("finder", FinderAgent(llm))
    orchestrator.register_agent("reviewer", ReviewerAgent(llm))

    # Override to stream each agent response
    original_get = orchestrator._get_agent_response

    async def streaming_get(agent_name, user_query, conversation):
        # Send thinking status
        await _safe_send(websocket, {
            "type": "status_update",
            "payload": {"agent": agent_name, "status": "thinking"},
        })

        response = await original_get(agent_name, user_query, conversation)

        # Send the agent message
        if response.contribution_type != "PASS":
            msg_id = str(uuid.uuid4())
            await _safe_send(websocket, {
                "type": "agent_message",
                "payload": {
                    "id": msg_id,
                    "agent": response.agent,
                    "contributionType": response.contribution_type,
                    "content": response.content,
                    "addressedTo": response.addressed_to,
                    "timestamp": datetime.now(tz=UTC).isoformat(),
                    "session_id": session_id,
                },
            })

            # Persist agent message
            if session_id:
                db = _get_db()
                try:
                    db.add_message(
                        session_id=session_id,
                        agent=response.agent,
                        content=response.content,
                        contribution_type=response.contribution_type,
                        addressed_to=response.addressed_to or "",
                    )
                finally:
                    db.close()

        # Send done status
        await _safe_send(websocket, {
            "type": "status_update",
            "payload": {"agent": agent_name, "status": "done"},
        })

        return response

    orchestrator._get_agent_response = streaming_get

    result = await orchestrator.run(augmented_query)

    # Send completion
    await _safe_send(websocket, {
        "type": "status_update",
        "payload": {
            "status": "complete",
            "session_id": session_id,
            "terminated_reason": result.terminated_reason,
            "round_count": result.round_count,
        },
    })

    return result


# For uvicorn direct run: uvicorn backend.main:app
app = create_app()
