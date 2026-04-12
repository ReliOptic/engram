"""Build panel — unified Start/Pause/Stop, file processing, embedding."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db_builder.chunking.base import SemanticChunker, MarkdownChunker, count_tokens
from db_builder.config import DBBuilderConfig
from db_builder.database import DatabaseManager
from db_builder.embedding.client import EmbeddingClient
from db_builder.embedding.embedder import BatchProgress
from db_builder.enrichment import LLMEnricher
from db_builder.filetype import detect_mime
from db_builder.pipeline import EmbeddingPipeline
from db_builder.store.chromadb_writer import ChromaDBWriter

logger = logging.getLogger(__name__)


class BuildWorker(QThread):
    """Process pending files → chunk → embed → ChromaDB. Supports pause."""

    log = Signal(str)
    file_started = Signal(int, str)         # file_id, path
    file_progress = Signal(int, str, int)   # file_id, stage, percent
    file_done = Signal(int, str)            # file_id, status
    overall = Signal(int, int, str)         # done_count, total, phase_label
    embed_progress = Signal(int, int)       # completed, total
    finished = Signal()

    def __init__(self, db_path: str, config: DBBuilderConfig,
                 file_ids: list[int], max_concurrent: int = 3,
                 enable_enrichment: bool = False):
        super().__init__()
        self._db_path = db_path  # path, not connection — will create own in run()
        self.db: DatabaseManager | None = None
        self.config = config
        self.file_ids = file_ids
        self.max_concurrent = max_concurrent
        self.enable_enrichment = enable_enrichment

        self._stop = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def stop(self):
        self._stop = True
        self._pause_event.set()  # unblock if paused

    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def run(self):
        # Create own DB connection for this thread
        self.db = DatabaseManager(self._db_path)
        self.db.init_schema()

        total = len(self.file_ids)
        self.log.emit(f"Build started: {total} file(s)")

        done = 0
        for i, fid in enumerate(self.file_ids):
            self._pause_event.wait()
            if self._stop:
                self.log.emit(f"Stopped at {done}/{total}")
                break

            self.overall.emit(done, total, "Processing files")
            self._process_one(fid)
            done += 1

        self.overall.emit(done, total, "Embedding")

        if not self._stop:
            self._run_embedding()

        self.overall.emit(done, total, "Done")
        self.log.emit(f"Build finished: {done}/{total} file(s)")
        self.db.close()
        self.finished.emit()

    # ── file processing ──

    def _process_one(self, file_id: int):
        f = self.db.get_file_by_id(file_id)
        if not f:
            return

        path = f["file_path"]
        self.file_started.emit(file_id, path)
        self.log.emit(f"  [{f['source_type']}] {path}")

        try:
            raw = self.config.raw_data_dir / path
            if not raw.exists():
                raise FileNotFoundError(f"File not found: {raw}")

            mime = detect_mime(raw)

            # ── Stage 1: Parse ──
            self.db.update_file_status(file_id, "parsing")
            self.file_progress.emit(file_id, "Parsing", 10)

            text = self._extract_text(raw, mime)
            if not text.strip():
                raise ValueError("No text content extracted")

            self.log.emit(f"    Parsed: {len(text)} chars, MIME={mime}")

            # ── Stage 2: Chunk ──
            self.file_progress.emit(file_id, "Chunking", 30)
            filename = Path(path).name

            if mime == "text/markdown" or path.endswith(".md"):
                chunker = MarkdownChunker(max_tokens=1024, min_tokens=50)
                chunks = chunker.chunk_markdown(text, filename, f["source_type"])
            else:
                chunker = SemanticChunker(max_tokens=1024, min_tokens=50)
                chunks = chunker.chunk_text(
                    text, filename, f["source_type"],
                    section_title=Path(path).stem,
                )

            # Fallback: if no chunks, make one from full text
            if not chunks:
                from db_builder.chunking.base import Chunk, generate_chunk_id, count_tokens as ct
                chunks = [Chunk(
                    id=generate_chunk_id(filename, "full", 0),
                    text=text[:3000],
                    token_count=ct(text[:3000]),
                    source_file=filename,
                    source_type=f["source_type"],
                    section_title=Path(path).stem,
                )]

            self.log.emit(f"    Chunked: {len(chunks)} chunk(s)")

            # ── Stage 3: LLM Enrichment (optional) ──
            enricher = None
            if self.enable_enrichment:
                self.file_progress.emit(file_id, f"Enriching 0/{len(chunks)}", 50)
                try:
                    enricher = LLMEnricher(
                        api_key=self.config.embedding.api_key,
                        base_url=self.config.embedding.base_url,
                    )
                except Exception as e:
                    self.log.emit(f"    LLM enrichment unavailable: {e}")
            else:
                self.file_progress.emit(file_id, "Saving", 60)

            # Detect tool family from filename (fast fallback)
            default_tool = "general"
            fp_lower = path.lower()
            for kw, t in [("prove", "PROVE"), ("aims", "AIMS"), ("wlcd", "WLCD")]:
                if kw in fp_lower:
                    default_tool = t
                    break

            total_quality = 0.0
            for ci, chunk in enumerate(chunks):
                tool_family = default_tool
                language = "en"
                is_safety = False
                summary = ""
                keywords_json = None
                xrefs_json = None

                if enricher:
                    self.file_progress.emit(
                        file_id, f"Enriching {ci+1}/{len(chunks)}",
                        50 + int(30 * ci / len(chunks)),
                    )
                    try:
                        result = enricher.enrich_chunk(chunk.text)
                        tool_family = result.tool_family
                        language = result.language
                        is_safety = result.is_safety_critical
                        summary = result.summary
                        if result.title:
                            chunk.section_title = result.title
                        if result.keywords:
                            keywords_json = json.dumps(result.keywords)
                        if result.cross_references:
                            xrefs_json = json.dumps(result.cross_references)
                    except Exception:
                        pass

                quality = min(1.0, max(0.3, chunk.token_count / 200))
                total_quality += quality

                self.db.insert_chunk({
                    "id": chunk.id, "file_id": file_id,
                    "text": chunk.text,
                    "token_count": chunk.token_count,
                    "chunk_type": "manual",
                    "source_file": filename,
                    "source_type": f["source_type"],
                    "tool_family": tool_family,
                    "customer": "generic", "silo_key": "",
                    "section_title": chunk.section_title or summary,
                    "section_path": json.dumps(chunk.section_path) if chunk.section_path else None,
                    "language": language,
                    "is_safety_critical": 1 if is_safety else 0,
                    "cross_references": xrefs_json,
                    "quality_score": quality,
                    "status": "accepted",
                    "page_number": chunk.page_number,
                })

            if enricher:
                enricher.close()

            avg_q = total_quality / len(chunks) if chunks else 0
            self.db.update_file_status(
                file_id, "chunked",
                chunk_count=len(chunks), avg_quality=round(avg_q, 3),
            )
            self.file_progress.emit(file_id, f"Done ({len(chunks)} chunks)", 90)
            self.file_done.emit(file_id, "chunked")
            self.log.emit(f"    Done: {len(chunks)} chunks, avg_quality={avg_q:.2f}")

        except Exception as e:
            self.db.update_file_status(file_id, "failed", error_message=str(e))
            self.file_done.emit(file_id, "failed")
            self.log.emit(f"    ERROR: {e}")

    def _extract_text(self, file_path: Path, mime: str) -> str:
        """Extract text from a file based on its MIME type."""
        # Text-based files
        if mime in ("text/plain", "text/markdown", "text/csv"):
            return file_path.read_text(encoding="utf-8", errors="replace")

        # PDF
        if mime == "application/pdf":
            try:
                import pymupdf4llm
                return pymupdf4llm.to_markdown(str(file_path))
            except Exception as e:
                self.log.emit(f"    pymupdf4llm failed, trying pdfplumber: {e}")
                try:
                    import pdfplumber
                    with pdfplumber.open(file_path) as pdf:
                        pages = [p.extract_text() or "" for p in pdf.pages]
                        return "\n\n".join(pages)
                except Exception as e2:
                    raise ValueError(f"PDF extraction failed: {e2}") from e2

        # Excel
        if "spreadsheet" in mime or "excel" in mime:
            import pandas as pd
            try:
                xl = pd.ExcelFile(file_path)
                parts = []
                for sheet in xl.sheet_names:
                    df = pd.read_excel(xl, sheet_name=sheet)
                    header = f"[Sheet: {sheet} | Columns: {' | '.join(str(c) for c in df.columns)}]"
                    for _, row in df.iterrows():
                        row_text = " | ".join(str(v) for v in row.values if pd.notna(v))
                        if row_text.strip():
                            parts.append(f"{header}\n{row_text}")
                return "\n\n".join(parts)
            except Exception as e:
                raise ValueError(f"Excel extraction failed: {e}") from e

        # Word
        if "wordprocessing" in mime or "msword" in mime:
            try:
                from docx import Document
                doc = Document(str(file_path))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                return "\n\n".join(paragraphs)
            except Exception as e:
                raise ValueError(f"Word extraction failed: {e}") from e

        # Images — OCR
        if mime.startswith("image/"):
            try:
                import pytesseract
                from PIL import Image
                img = Image.open(file_path)
                return pytesseract.image_to_string(img, lang="eng+deu")
            except Exception as e:
                raise ValueError(f"OCR failed: {e}") from e

        # Fallback: try reading as text
        try:
            return file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            raise ValueError(f"Unsupported file type: {mime}")

    # ── embedding ──

    def _run_embedding(self):
        pending = self.db.get_pending_embedding_chunks(limit=99999)
        if not pending:
            self.log.emit("No chunks to embed.")
            return

        self.log.emit(f"Embedding {len(pending)} chunk(s)...")

        try:
            client = EmbeddingClient(
                api_key=self.config.embedding.api_key,
                base_url=self.config.embedding.base_url,
                model=self.config.embedding.model,
            )
            writer = ChromaDBWriter(self.config.chromadb_dir)

            def on_prog(p: BatchProgress):
                self.embed_progress.emit(p.completed_chunks, p.total_chunks)

            pipeline = EmbeddingPipeline(
                db=self.db, embedding_client=client, chromadb_writer=writer,
                batch_size=self.config.embedding_batch_size,
                cost_per_million=self.config.embedding.cost_per_million_input,
                on_progress=on_prog,
            )
            result = pipeline.run()

            for fid in self.file_ids:
                fi = self.db.get_file_by_id(fid)
                if fi and fi["status"] == "chunked":
                    self.db.update_file_status(fid, "completed")

            self.log.emit(
                f"Embedded: {result.completed_chunks} chunks, "
                f"{result.total_tokens} tokens, ${result.estimated_cost_usd:.4f}"
            )
            stats = writer.get_collection_stats("zemas_manuals")
            self.log.emit(f"ChromaDB: {stats['count']} total chunks")
            client.close()

            # Generate wiki index (only with enrichment enabled)
            if self.enable_enrichment:
                self._generate_wiki_index()

        except Exception as e:
            self.log.emit(f"Embedding ERROR: {e}")

    def _generate_wiki_index(self):
        """Generate wiki index.md from all chunks."""
        try:
            rows = self.db.conn.execute(
                "SELECT DISTINCT source_file, tool_family, section_title, source_type "
                "FROM chunks WHERE status = 'accepted' "
                "ORDER BY tool_family, source_file"
            ).fetchall()
            if not rows:
                return

            docs = [
                {
                    "source_file": r["source_file"],
                    "tool_family": r["tool_family"],
                    "title": r["section_title"] or r["source_file"],
                    "summary": "",
                    "source_type": r["source_type"],
                }
                for r in rows
            ]
            enricher = LLMEnricher(
                api_key=self.config.embedding.api_key,
                base_url=self.config.embedding.base_url,
            )
            index_path = self.config.raw_data_dir.parent / "wiki_index.md"
            enricher.generate_index(docs, index_path)
            enricher.close()
            self.log.emit(f"Wiki index: {index_path}")
        except Exception as e:
            self.log.emit(f"Wiki index generation skipped: {e}")


# ── Styles ──

_BTN = (
    "QPushButton{{background:{bg};color:white;font-weight:bold;"
    "border-radius:4px;padding:6px 24px;font-size:13px}}"
    "QPushButton:hover{{background:{hover}}}"
    "QPushButton:disabled{{background:#bbb;color:#eee}}"
)
S_START = _BTN.format(bg="#4CAF50", hover="#388E3C")
S_PAUSE = _BTN.format(bg="#FF9800", hover="#F57C00")
S_RESUME = _BTN.format(bg="#2196F3", hover="#1976D2")
S_STOP = _BTN.format(bg="#F44336", hover="#D32F2F")


class BuildPanel(QWidget):
    """Unified build controls: Start / Pause / Resume / Stop."""

    build_finished = Signal()

    def __init__(self, db: DatabaseManager, config: DBBuilderConfig, parent=None):
        super().__init__(parent)
        self.db = db
        self.config = config
        self._worker: BuildWorker | None = None
        self._state = "idle"  # idle | running | paused

        self._setup_ui()
        self._update_button_state()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        # ── Toolbar ──
        bar = QHBoxLayout()

        self.btn_main = QPushButton("Start Build")
        self.btn_main.setMinimumHeight(38)
        self.btn_main.clicked.connect(self._on_main_clicked)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setMinimumHeight(38)
        self.btn_stop.setStyleSheet(S_STOP)
        self.btn_stop.clicked.connect(self._on_stop)

        lbl = QLabel("Max files:")
        self.spin = QSpinBox()
        self.spin.setRange(1, 10)
        self.spin.setValue(3)
        self.spin.setMinimumHeight(30)

        from PySide6.QtWidgets import QCheckBox
        self.chk_enrich = QCheckBox("LLM Enrichment")
        self.chk_enrich.setToolTip(
            "Enable LLM analysis for each chunk (title, keywords, cross-refs).\n"
            "Slower but higher quality. Uses Gemini Flash Lite (free)."
        )
        self.chk_enrich.setChecked(False)

        self.lbl_pending = QLabel()
        self.lbl_pending.setStyleSheet("color:#888;font-size:12px;")

        bar.addWidget(self.btn_main)
        bar.addWidget(self.btn_stop)
        bar.addSpacing(16)
        bar.addWidget(lbl)
        bar.addWidget(self.spin)
        bar.addSpacing(12)
        bar.addWidget(self.chk_enrich)
        bar.addSpacing(16)
        bar.addWidget(self.lbl_pending)
        bar.addStretch()
        root.addLayout(bar)

        # ── Progress bars ──
        p1 = QHBoxLayout()
        self.lbl_phase = QLabel("Idle")
        self.lbl_phase.setStyleSheet("font-size:12px;color:#666;min-width:120px;")
        self.prog_overall = QProgressBar()
        self.prog_overall.setMaximumHeight(22)
        p1.addWidget(self.lbl_phase)
        p1.addWidget(self.prog_overall, 1)
        root.addLayout(p1)

        p2 = QHBoxLayout()
        self.lbl_embed = QLabel("Embedding:")
        self.lbl_embed.setStyleSheet("font-size:12px;color:#666;min-width:120px;")
        self.prog_embed = QProgressBar()
        self.prog_embed.setMaximumHeight(22)
        self.lbl_embed.hide()
        self.prog_embed.hide()
        p2.addWidget(self.lbl_embed)
        p2.addWidget(self.prog_embed, 1)
        root.addLayout(p2)

        # ── Splitter: table + log ──
        split = QSplitter(Qt.Orientation.Vertical)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["File", "Type", "Stage", "Progress"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(
            "QTableWidget{gridline-color:#e0e0e0;font-size:12px}"
            "QHeaderView::section{background:#f5f5f5;padding:6px;"
            "border:1px solid #ddd;font-weight:bold}"
        )
        split.addWidget(self.table)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(
            "QTextEdit{background:#1e1e1e;color:#d4d4d4;"
            "font-family:'Consolas','Courier New',monospace;font-size:11px}"
        )
        split.addWidget(self.log)
        split.setSizes([280, 280])
        root.addWidget(split)

        self._refresh_pending_count()

    # ── State machine ──

    def _update_button_state(self):
        if self._state == "idle":
            self.btn_main.setText("Start Build")
            self.btn_main.setStyleSheet(S_START)
            self.btn_main.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self.spin.setEnabled(True)
        elif self._state == "running":
            self.btn_main.setText("Pause")
            self.btn_main.setStyleSheet(S_PAUSE)
            self.btn_main.setEnabled(True)
            self.btn_stop.setEnabled(True)
            self.spin.setEnabled(False)
        elif self._state == "paused":
            self.btn_main.setText("Resume")
            self.btn_main.setStyleSheet(S_RESUME)
            self.btn_main.setEnabled(True)
            self.btn_stop.setEnabled(True)
            self.spin.setEnabled(False)

    def _on_main_clicked(self):
        if self._state == "idle":
            self._start_build()
        elif self._state == "running":
            self._pause_build()
        elif self._state == "paused":
            self._resume_build()

    def _on_stop(self):
        if self._worker:
            self._worker.stop()
            self._append_log("Stopping... (finishing current file)")

    # ── Build lifecycle ──

    def _start_build(self):
        pending = self.db.list_files(status="pending")
        if not pending:
            self._append_log("No pending files. Add files in the Files tab first.")
            return

        ids = [f["id"] for f in pending]

        # Populate table
        self.table.setRowCount(len(pending))
        self._row_map = {}
        for row, f in enumerate(pending):
            self._row_map[f["id"]] = row
            self.table.setItem(row, 0, QTableWidgetItem(f["file_path"]))
            self.table.setItem(row, 1, QTableWidgetItem(f["source_type"]))
            item = QTableWidgetItem("Waiting")
            item.setForeground(QColor("#888"))
            self.table.setItem(row, 2, item)
            bar = QProgressBar()
            bar.setMaximum(100)
            bar.setValue(0)
            bar.setMaximumHeight(18)
            self.table.setCellWidget(row, 3, bar)

        self.prog_overall.setMaximum(len(pending))
        self.prog_overall.setValue(0)
        self.lbl_phase.setText(f"0 / {len(pending)} files")
        self.lbl_embed.hide()
        self.prog_embed.hide()

        self._state = "running"
        self._update_button_state()

        self._worker = BuildWorker(
            self.db.db_path, self.config, ids, self.spin.value(),
            enable_enrichment=self.chk_enrich.isChecked(),
        )
        self._worker.log.connect(self._append_log)
        self._worker.file_started.connect(self._w_file_started)
        self._worker.file_progress.connect(self._w_file_progress)
        self._worker.file_done.connect(self._w_file_done)
        self._worker.overall.connect(self._w_overall)
        self._worker.embed_progress.connect(self._w_embed)
        self._worker.finished.connect(self._w_finished)
        self._worker.start()

    def _pause_build(self):
        if self._worker:
            self._worker.pause()
        self._state = "paused"
        self._update_button_state()
        self._append_log("Paused.")

    def _resume_build(self):
        if self._worker:
            self._worker.resume()
        self._state = "running"
        self._update_button_state()
        self._append_log("Resumed.")

    # ── Worker signals ──

    def _w_file_started(self, fid: int, path: str):
        row = self._row_map.get(fid)
        if row is None:
            return
        it = self.table.item(row, 2)
        if it:
            it.setText("Processing")
            it.setForeground(QColor("#2196F3"))

    def _w_file_progress(self, fid: int, stage: str, pct: int):
        row = self._row_map.get(fid)
        if row is None:
            return
        it = self.table.item(row, 2)
        if it:
            it.setText(stage)
        bar = self.table.cellWidget(row, 3)
        if isinstance(bar, QProgressBar):
            bar.setValue(pct)

    def _w_file_done(self, fid: int, status: str):
        row = self._row_map.get(fid)
        if row is None:
            return
        it = self.table.item(row, 2)
        bar = self.table.cellWidget(row, 3)
        if status == "failed":
            if it:
                # Get error message from DB
                # Read from main thread's DB (worker wrote to same file)
                try:
                    main_db = DatabaseManager(self.config.db_path)
                    f = main_db.get_file_by_id(fid)
                    err = f.get("error_message", "") if f else ""
                    main_db.close()
                except Exception:
                    err = ""
                short_err = err[:60] + "..." if len(err) > 60 else err
                it.setText(f"FAILED: {short_err}" if short_err else "FAILED")
                it.setToolTip(f"Error: {err}" if err else "")
                it.setForeground(QColor("#F44336"))
        else:
            if it:
                it.setText("Done")
                it.setForeground(QColor("#4CAF50"))
            if isinstance(bar, QProgressBar):
                bar.setValue(100)

    def _w_overall(self, done: int, total: int, phase: str):
        self.prog_overall.setValue(done)
        self.lbl_phase.setText(f"{done} / {total} files — {phase}")

    def _w_embed(self, done: int, total: int):
        self.lbl_embed.show()
        self.prog_embed.show()
        self.prog_embed.setMaximum(total)
        self.prog_embed.setValue(done)
        self.lbl_embed.setText(f"Embedding: {done}/{total}")

    def _w_finished(self):
        self._state = "idle"
        self._update_button_state()
        self.lbl_phase.setText("Complete!")
        self._refresh_pending_count()
        self.build_finished.emit()

    # ── Helpers ──

    def _refresh_pending_count(self):
        count = len(self.db.list_files(status="pending"))
        self.lbl_pending.setText(f"{count} pending file(s)" if count else "No pending files")

    def _append_log(self, msg: str):
        self.log.append(msg)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())
