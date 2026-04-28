"""Engram FastAPI application.

Entry point for the backend server. Provides:
- /health endpoint
- /ws WebSocket for agent chat (with session persistence)
- /api/config/* endpoints for frontend config loading
- /api/cases/* endpoints for case management
- /api/sessions/* endpoints for session/message persistence
- /api/settings/* endpoints for admin configuration
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import logging

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import VERSION, load_dropdowns_config, load_models_config
import backend.config as _cfg

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})
_IMAGE_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
}


async def _ocr_image(content: bytes, filename: str) -> str:
    """Extract visible text from an image via OpenRouter vision API.

    Returns empty string when API key is absent, file is not an image,
    or the API call fails — callers must treat this as optional enrichment.
    """
    import base64
    import httpx

    api_key = getattr(_cfg, "OPENROUTER_API_KEY", "")
    if not api_key:
        return ""
    ext = Path(filename).suffix.lower()
    if ext not in _IMAGE_EXTENSIONS:
        return ""

    mime = _IMAGE_MIME.get(ext, "image/jpeg")
    b64 = base64.b64encode(content).decode()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "google/gemini-2.0-flash-lite-001",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Extract all visible text from this image. "
                                    "Output only the extracted text, no commentary."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            },
                        ],
                    }],
                    "max_tokens": 1000,
                },
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("OCR failed for %s: %s", filename, exc)
    return ""


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

class SessionCloseRequest(BaseModel):
    resolution: str = ""

class FeedbackRequest(BaseModel):
    helpful: bool


async def _dreaming_loop(app: FastAPI, *, run_immediately: bool = False) -> None:  # type: ignore[type-arg]
    """Background task: run DreamingPipeline once daily at 02:00 local time."""
    from backend.knowledge.dreaming import DreamingPipeline
    from backend.knowledge.vectordb import VectorDB

    if not run_immediately:
        now = datetime.now()
        next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())

    while True:
        try:
            vdb = VectorDB(persist_dir=str(_cfg.DATA_DIR / "chroma_db"))
            pipeline = DreamingPipeline(vdb)
            await pipeline.run_full_cycle()
            app.state.db.record_dreaming_run("ok")
        except Exception as exc:
            logger.error("Dreaming pipeline failed: %s", exc)
            app.state.db.record_dreaming_run("failed", str(exc))

        now = datetime.now()
        next_run = now.replace(hour=2, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())


def create_app() -> FastAPI:
    """Factory function for creating the FastAPI app."""
    from contextlib import asynccontextmanager
    from backend.knowledge.database import EngramDB

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        from backend.knowledge.auto_ingester import AutoIngester
        from backend.knowledge.vectordb import VectorDB
        from backend.memory.case_recorder import CaseRecorder
        watch_dir = _cfg.DATA_DIR / "weekly_reports"
        watch_dir.mkdir(parents=True, exist_ok=True)
        vdb = VectorDB(persist_dir=str(_cfg.DATA_DIR / "chroma_db"))
        ingester = AutoIngester(watch_dir, vdb)
        asyncio.create_task(ingester.run_watcher())
        asyncio.create_task(_dreaming_loop(app))
        if not hasattr(app.state, "case_recorder") or app.state.case_recorder is None:
            app.state.case_recorder = CaseRecorder(vdb, app.state.db)
        yield

    app = FastAPI(
        title="Engram",
        description="Multi-Agent Support System",
        version=VERSION,
        lifespan=_lifespan,
    )

    # Load config eagerly so it's available immediately (works with test clients too)
    app.state.models_config = load_models_config()
    app.state.dropdowns_config = load_dropdowns_config()
    app.state.db = EngramDB(str(_cfg.DATA_DIR / "sqlite" / "engram.db"))

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
            return {"enabled": False, "status": "disabled", "pending_events": 0, "server_url": None, "online": None}
        try:
            from backend.sync.queue import SyncQueue
            queue = SyncQueue(app.state.db._conn)
            from backend.sync.client import SyncClient
            client = SyncClient(SYNC_SERVER_URL, queue, SYNC_DEVICE_NAME)
            return client.get_status()
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

                    # Append OCR-extracted image text to query context
                    for att in payload.get("attachments", []):
                        extracted = (att.get("extracted_text") or "").strip()
                        if extracted:
                            text = f"{text}\n\n[Attached image text: {extracted}]"

                    # Auto-create session on first message if no session_id
                    db = app.state.db
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
        return await asyncio.to_thread(
            app.state.db.list_cases, account=account, tool=tool, status=status, limit=limit
        )

    # --- Sessions API ---

    @app.post("/api/sessions")
    async def create_session(body: SessionCreate):
        db = app.state.db
        session_id = await asyncio.to_thread(
            db.create_session,
            title=body.title,
            silo_account=body.silo_account,
            silo_tool=body.silo_tool,
            silo_component=body.silo_component,
        )
        return await asyncio.to_thread(db.get_session, session_id)

    @app.get("/api/sessions")
    async def list_sessions(status: str | None = None, limit: int = 50):
        return await asyncio.to_thread(app.state.db.list_sessions, status=status, limit=limit)

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        from fastapi.responses import JSONResponse
        db = app.state.db
        session = await asyncio.to_thread(db.get_session, session_id)
        if not session:
            return JSONResponse(status_code=404, content={"detail": "Session not found"})
        messages = await asyncio.to_thread(db.get_messages, session_id)
        return {**session, "messages": messages}

    @app.patch("/api/sessions/{session_id}")
    async def update_session(session_id: str, body: SessionUpdate):
        from fastapi.responses import JSONResponse
        db = app.state.db
        session = db.get_session(session_id)
        if not session:
            return JSONResponse(status_code=404, content={"detail": "Session not found"})
        if body.title is not None:
            db.update_session_title(session_id, body.title)
        if body.status == "archived":
            db.archive_session(session_id)
        return db.get_session(session_id)

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str):
        from fastapi.responses import JSONResponse
        db = app.state.db
        session = db.get_session(session_id)
        if not session:
            return JSONResponse(status_code=404, content={"detail": "Session not found"})
        db.delete_session(session_id)
        return {"ok": True}

    @app.post("/api/sessions/{session_id}/feedback")
    async def submit_feedback(session_id: str, body: FeedbackRequest):
        from fastapi.responses import JSONResponse
        db = app.state.db
        if not db.get_session(session_id):
            return JSONResponse(status_code=404, content={"detail": "Session not found"})
        if db.get_feedback(session_id) is not None:
            return JSONResponse(status_code=409, content={"detail": "Feedback already submitted"})
        result = db.record_feedback(session_id, body.helpful)
        return result

    @app.get("/api/sessions/{session_id}/feedback")
    async def get_feedback(session_id: str):
        from fastapi.responses import JSONResponse
        db = app.state.db
        feedback = db.get_feedback(session_id)
        if feedback is None:
            return JSONResponse(status_code=404, content={"detail": "No feedback found"})
        return feedback

    @app.post("/api/sessions/{session_id}/close")
    async def close_session(session_id: str, body: SessionCloseRequest):
        from fastapi.responses import JSONResponse
        db = app.state.db
        session = db.get_session(session_id)
        if not session:
            return JSONResponse(status_code=404, content={"detail": "Session not found"})
        if session["status"] == "closed":
            return JSONResponse(status_code=409, content={"detail": "Session already closed"})

        messages = db.get_messages(session_id)
        conversation_text = "\n".join(
            f"[{m['agent']}]: {m['content']}" for m in messages
        )

        tacit_signals: list[dict] = []
        try:
            from backend.utils.llm_client import LLMClient
            from backend.knowledge.tacit_extractor import TacitExtractor
            llm = LLMClient(app.state.models_config)
            extractor = TacitExtractor(llm)
            tacit_signals = await extractor.extract(conversation_text)
        except Exception:
            pass

        from backend.agents.orchestrator import AgentResponse as _AgentResponse
        agent_responses: list[_AgentResponse] = [
            _AgentResponse(
                agent=m["agent"],
                contribution_type=m.get("contribution_type", ""),
                contribution_detail="",
                addressed_to=m.get("addressed_to", "") or "",
                content=m["content"],
            )
            for m in messages
        ]

        case_metadata = {
            "case_id": session_id,
            "account": session.get("silo_account", ""),
            "tool": session.get("silo_tool", ""),
            "component": session.get("silo_component", ""),
            "title": session.get("title", ""),
            "resolution": body.resolution,
        }

        recorder = app.state.case_recorder
        type_a_id, type_b_id = await recorder.record_case(case_metadata, agent_responses)

        db.close_session(session_id)

        return {
            "status": "closed",
            "type_a_id": type_a_id,
            "type_b_id": type_b_id,
            "tacit_count": len(tacit_signals),
        }

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

    @app.post("/api/settings/save-api-key")
    async def save_api_key(body: TestConnectionRequest):
        """Save API key to .env file so it persists across restarts.

        This is the in-app key setup flow: user enters key in Settings,
        it gets tested and saved to .env without manual file editing.
        """
        env_path = Path(__file__).parent.parent / ".env"
        env_var = "OPENROUTER_API_KEY" if body.provider == "openrouter" else "OPENAI_API_KEY"

        # Read existing .env (or create from template)
        if env_path.exists():
            lines = env_path.read_text().splitlines()
        else:
            template = Path(__file__).parent.parent / ".env.example"
            lines = template.read_text().splitlines() if template.exists() else []

        # Update or append the key
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{env_var}=") or line.startswith(f"# {env_var}="):
                new_lines.append(f"{env_var}={body.api_key}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"{env_var}={body.api_key}")

        env_path.write_text("\n".join(new_lines) + "\n")

        # Update runtime config
        import os
        os.environ[env_var] = body.api_key
        if body.provider == "openrouter":
            _cfg.OPENROUTER_API_KEY = body.api_key
        elif body.provider == "openai":
            _cfg.OPENAI_API_KEY = body.api_key

        return {"ok": True, "saved_to": str(env_path)}

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

        Saves to data/uploads/. For image files, extracts visible text via
        OpenRouter vision API and returns it as extracted_text.
        """
        upload_dir = _cfg.DATA_DIR / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}_{file.filename}"
        dest = upload_dir / safe_name

        content = await file.read()
        dest.write_bytes(content)

        extracted_text = await _ocr_image(content, file.filename or "")

        return {
            "filename": file.filename,
            "saved_as": str(dest),
            "size_bytes": len(content),
            "extracted_text": extracted_text or None,
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
        try:
            conn = app.state.db._conn
            row = conn.execute("SELECT COUNT(*) FROM cases").fetchone()
            result["cases"]["total"] = row[0] if row else 0

            row = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE created_at > datetime('now', '-7 days')"
            ).fetchone()
            result["cases"]["recent_7d"] = row[0] if row else 0

            row = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
            result["sessions_total"] = row[0] if row else 0
        except Exception:
            pass

        return result

    @app.get("/api/knowledge/health")
    async def get_knowledge_health():
        """Knowledge base health summary for the header indicator."""
        from backend.knowledge.vectordb import VectorDB, COLLECTIONS

        persist_dir = str(_cfg.DATA_DIR / "chroma_db")
        conn = app.state.db._conn

        total_chunks = 0
        try:
            vdb = VectorDB(persist_dir=persist_dir)
            for name in COLLECTIONS:
                try:
                    total_chunks += vdb.count(name)
                except Exception:
                    pass
        except Exception:
            pass

        total_cases = 0
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE status=\'closed\'"
            ).fetchone()
            total_cases = row[0] if row else 0
        except Exception:
            pass

        last_dreaming_run: str | None = None
        dreaming_status = "never_run"
        try:
            row = conn.execute(
                "SELECT run_at, status FROM dreaming_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                last_dreaming_run = row[0]
                dreaming_status = row[1] if row[1] in ("ok", "failed") else "ok"
        except Exception:
            pass

        weekly_files_processed = 0
        try:
            manifest_path = _cfg.DATA_DIR / "weekly_reports" / ".processed.json"
            if manifest_path.exists():
                import json as _json
                data = _json.loads(manifest_path.read_text())
                weekly_files_processed = len(data.get("processed", []))
        except Exception:
            pass

        feedback_positive_rate: float | None = None
        try:
            total_row = conn.execute("SELECT COUNT(*) FROM case_feedback").fetchone()
            total_fb = total_row[0] if total_row else 0
            if total_fb > 0:
                pos_row = conn.execute(
                    "SELECT COUNT(*) FROM case_feedback WHERE rating=\'positive\'"
                ).fetchone()
                pos_count = pos_row[0] if pos_row else 0
                feedback_positive_rate = round(pos_count / total_fb, 4)
        except Exception:
            pass

        return {
            "total_cases": total_cases,
            "total_chunks": total_chunks,
            "last_dreaming_run": last_dreaming_run,
            "dreaming_status": dreaming_status,
            "weekly_files_processed": weekly_files_processed,
            "feedback_positive_rate": feedback_positive_rate,
        }

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
            results = await vdb.async_search(collection, q, n_results=n, where=where)
            return {"results": results, "count": len(results)}
        except Exception as e:
            return {"results": [], "count": 0, "error": str(e)}

    @app.get("/api/chunks/{chunk_id}")
    async def get_chunk(chunk_id: str):
        """Retrieve a single chunk by ID, searching all collections."""
        from fastapi.responses import JSONResponse
        from backend.knowledge.vectordb import VectorDB, COLLECTIONS

        persist_dir = str(_cfg.DATA_DIR / "chroma_db")
        try:
            vdb = VectorDB(persist_dir=persist_dir)
            for collection in COLLECTIONS:
                chunk = vdb.get_by_id(collection, chunk_id)
                if chunk:
                    return {**chunk, "collection": collection}
        except Exception as e:
            logger.warning("chunk lookup error for %s: %s", chunk_id, e)
        return JSONResponse(status_code=404, content={"detail": f"Chunk '{chunk_id}' not found"})

    @app.post("/api/knowledge/ingest")
    async def trigger_ingest():
        """Manually scan data/weekly_reports/ and ingest any new xlsx files."""
        from backend.knowledge.auto_ingester import AutoIngester
        from backend.knowledge.vectordb import VectorDB

        watch_dir = _cfg.DATA_DIR / "weekly_reports"
        watch_dir.mkdir(parents=True, exist_ok=True)
        vdb = VectorDB(persist_dir=str(_cfg.DATA_DIR / "chroma_db"))
        ingester = AutoIngester(watch_dir, vdb)
        ingested = await ingester.scan_and_ingest()
        return {"ingested": ingested, "count": len(ingested)}

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
            app.state.db.add_message(session_id=session_id, agent="system", content=f"Echo: {query}")
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
                app.state.db.add_message(
                    session_id=session_id,
                    agent=response.agent,
                    content=response.content,
                    contribution_type=response.contribution_type,
                    addressed_to=response.addressed_to or "",
                )

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
