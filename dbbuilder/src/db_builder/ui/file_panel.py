"""File management panel — folder import, file list, context menu, status feedback."""

from __future__ import annotations

import os
import shutil
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db_builder.database import DatabaseManager
from db_builder.pipeline import FileScanner
from db_builder.ui.theme import (
    STATUS_DISPLAY, LOG_QSS, S_PRIMARY,
    C_TEXT_MUTED, C_TEXT_2, C_TEXT_FAINT,
    C_HAIR, C_BORDER, C_APP, C_SUNKEN, C_PANEL,
    C_INFO_SOFT, C_INFO_TEXT, C_BRAND,
    C_SUCCESS_SOFT, C_SUCCESS_TEXT, C_SUCCESS_EDGE,
    C_WARNING_SOFT, C_WARNING_TEXT, C_WARNING_EDGE,
    C_ERROR_SOFT, C_ERROR_TEXT, C_ERROR_EDGE,
)

logger = logging.getLogger(__name__)

TYPE_DISPLAY = {
    "manual": "PDF Manual", "weekly": "Excel Weekly", "sop": "Word SOP",
    "error_db": "Error DB", "cal_log": "Cal Log",
    "image": "Image/Scan", "misc": "Text/Other",
}

SUPPORTED_EXTS = {
    ".pdf", ".xlsx", ".xls", ".docx",
    ".png", ".jpg", ".jpeg", ".tiff", ".bmp",
    ".md", ".txt", ".csv",
}


# ── Workers ──

class ImportWorker(QThread):
    """Copy files into raw_data_dir. Returns ALL dest paths (copied + existing)."""

    file_copying = Signal(str, int, int)   # filename, current, total
    log_message = Signal(str)
    finished = Signal(list)                # list of dest Path strings (all files)

    def __init__(self, source_dir: Path, raw_data_dir: Path):
        super().__init__()
        self.source_dir = source_dir
        self.raw_data_dir = raw_data_dir

    def run(self):
        files = [
            f for f in self.source_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
        ]
        total = len(files)
        if total == 0:
            self.log_message.emit("No supported files found.")
            self.finished.emit([])
            return

        all_dest_paths: list[str] = []
        copied = 0
        for i, src in enumerate(files):
            name = src.name
            self.file_copying.emit(name, i + 1, total)
            try:
                rel = src.relative_to(self.source_dir)
                dest = self.raw_data_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)

                if dest.exists() and src.stat().st_size == dest.stat().st_size:
                    # Already there, but still register in DB
                    all_dest_paths.append(str(dest))
                    continue

                shutil.copy2(src, dest)
                all_dest_paths.append(str(dest))
                copied += 1
                size_kb = src.stat().st_size / 1024
                self.log_message.emit(f"  {name} ({size_kb:.0f} KB)")
            except Exception as e:
                self.log_message.emit(f"  ERROR: {name}: {e}")

        self.log_message.emit(f"Done: {copied} copied, {total - copied} existing")
        self.finished.emit(all_dest_paths)


class ScanWorker(QThread):
    finished = Signal(list)
    log_message = Signal(str)

    def __init__(self, scanner: FileScanner):
        super().__init__()
        self.scanner = scanner

    def run(self):
        self.log_message.emit("Scanning for new/changed files...")
        results = self.scanner.scan()
        self.log_message.emit(f"Scan: {len(results)} new/changed file(s)")
        self.finished.emit(results)


# ── Notification banner ──

class NotificationBanner(QFrame):
    """Colored banner with message and action button."""

    action_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)

        self.icon_label = QLabel()
        self.icon_label.setFixedWidth(20)
        self.msg_label = QLabel()
        self.msg_label.setStyleSheet("font-size: 12px; font-weight: bold;")

        self.btn = QPushButton()
        self.btn.setFixedHeight(28)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.clicked.connect(self.action_clicked.emit)

        self.btn_dismiss = QPushButton("x")
        self.btn_dismiss.setFixedSize(24, 24)
        self.btn_dismiss.setStyleSheet(
            f"QPushButton{{border:none;color:{C_TEXT_MUTED};font-weight:700;font-size:14px}}"
            f"QPushButton:hover{{color:{C_TEXT_2}}}"
        )
        self.btn_dismiss.clicked.connect(self.hide)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.msg_label, 1)
        layout.addWidget(self.btn)
        layout.addWidget(self.btn_dismiss)

    def show_info(self, msg: str, button_text: str = ""):
        self.setStyleSheet(
            f"QFrame{{background:{C_INFO_SOFT};border:1px solid {C_BRAND};border-radius:6px}}"
        )
        self.icon_label.setText("i")
        self.icon_label.setStyleSheet(f"color:{C_BRAND};font-weight:700;font-size:15px;")
        self.msg_label.setText(msg)
        self.msg_label.setStyleSheet(f"color:{C_INFO_TEXT};font-size:12px;font-weight:600;")
        if button_text:
            self.btn.setText(button_text)
            self.btn.setStyleSheet(
                f"QPushButton{{background:{C_BRAND};color:white;border-radius:6px;"
                f"padding:2px 14px;font-weight:700;font-size:11px;border:none}}"
                f"QPushButton:hover{{background:#1A2BA8}}"
            )
            self.btn.show()
        else:
            self.btn.hide()
        self.show()

    def show_success(self, msg: str):
        self.setStyleSheet(
            f"QFrame{{background:{C_SUCCESS_SOFT};border:1px solid {C_SUCCESS_EDGE};border-radius:6px}}"
        )
        self.icon_label.setText("✓")
        self.icon_label.setStyleSheet(f"color:{C_SUCCESS_TEXT};font-weight:700;font-size:14px;")
        self.msg_label.setText(msg)
        self.msg_label.setStyleSheet(f"color:{C_SUCCESS_TEXT};font-size:12px;font-weight:600;")
        self.btn.hide()
        self.show()

    def show_progress(self, msg: str):
        self.setStyleSheet(
            f"QFrame{{background:{C_WARNING_SOFT};border:1px solid {C_WARNING_EDGE};border-radius:6px}}"
        )
        self.icon_label.setText("…")
        self.icon_label.setStyleSheet(f"color:{C_WARNING_TEXT};font-weight:700;font-size:14px;")
        self.msg_label.setText(msg)
        self.msg_label.setStyleSheet(f"color:{C_WARNING_TEXT};font-size:12px;font-weight:600;")
        self.btn.hide()
        self.btn_dismiss.hide()
        self.show()


# ── Main panel ──

class FilePanel(QWidget):
    """File list with import, context menu, progress, and build suggestions."""

    request_build = Signal()  # emitted when user clicks "Build Now" in banner

    def __init__(self, db: DatabaseManager, raw_data_dir: Path, parent=None):
        super().__init__(parent)
        self.db = db
        self.raw_data_dir = raw_data_dir
        self._workers: list[QThread] = []
        self._row_file_ids: list[int] = []

        self._setup_ui()
        self._refresh_table()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Notification banner ──
        self.banner = NotificationBanner()
        self.banner.action_clicked.connect(self._on_banner_build)
        layout.addWidget(self.banner)

        # ── Toolbar ──
        toolbar = QHBoxLayout()

        self.btn_add_folder = QPushButton("Add Folder...")
        self.btn_add_folder.setMinimumHeight(34)
        self.btn_add_folder.setStyleSheet(S_PRIMARY)
        self.btn_add_folder.clicked.connect(self._on_add_folder)

        self.btn_add_files = QPushButton("Add Files...")
        self.btn_add_files.setMinimumHeight(34)
        self.btn_add_files.clicked.connect(self._on_add_files)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setMinimumHeight(34)
        self.btn_refresh.clicked.connect(self._on_refresh)

        self.label_summary = QLabel()
        self.label_summary.setStyleSheet(f"color:{C_TEXT_MUTED};font-size:12px;")

        toolbar.addWidget(self.btn_add_folder)
        toolbar.addWidget(self.btn_add_files)
        toolbar.addWidget(self.btn_refresh)
        toolbar.addStretch()
        toolbar.addWidget(self.label_summary)
        layout.addLayout(toolbar)

        # ── Progress area ──
        self.progress_frame = QFrame()
        self.progress_frame.setVisible(False)
        pf_layout = QVBoxLayout(self.progress_frame)
        pf_layout.setContentsMargins(0, 0, 0, 0)
        pf_layout.setSpacing(2)

        self.progress_label = QLabel("Importing...")
        self.progress_label.setStyleSheet(f"font-size:11px;color:{C_TEXT_2};")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(18)
        self.progress_bar.setTextVisible(True)

        pf_layout.addWidget(self.progress_label)
        pf_layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_frame)

        # ── Splitter: table + log ──
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Status", "File Name", "Type", "Size", "Chunks", "Quality"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        # Table styling comes from GLOBAL_QSS; only override item padding
        self.table.setStyleSheet("QTableWidget::item{padding:4px 6px;}")
        splitter.addWidget(self.table)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(140)
        self.log_text.setStyleSheet(LOG_QSS)
        splitter.addWidget(self.log_text)
        splitter.setSizes([500, 140])
        layout.addWidget(splitter)

    # ── Progress helpers ──

    def _show_progress(self, label: str, current: int = 0, total: int = 0):
        self.progress_frame.setVisible(True)
        self.progress_label.setText(label)
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{current}/{total}")
        else:
            self.progress_bar.setMaximum(0)  # indeterminate
            self.progress_bar.setFormat("")

    def _hide_progress(self):
        self.progress_frame.setVisible(False)

    # ── Import ──

    def _on_add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder to Import", "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if not folder:
            return
        self._start_import(Path(folder))

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Files to Import", "",
            "All Supported (*.pdf *.xlsx *.xls *.docx *.png *.jpg *.jpeg "
            "*.tiff *.bmp *.md *.txt *.csv);;"
            "PDF (*.pdf);;Excel (*.xlsx *.xls);;Word (*.docx);;"
            "Images (*.png *.jpg *.jpeg *.tiff *.bmp);;Text (*.md *.txt *.csv)"
        )
        if not files:
            return

        # Copy selected files into a temp dir, then import from there
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        for f in files:
            shutil.copy2(f, tmp / Path(f).name)
        self._start_import(tmp)

    def _start_import(self, source_dir: Path):
        self._set_busy(True)
        self.banner.show_progress(f"Importing from {source_dir.name}...")

        worker = ImportWorker(source_dir, self.raw_data_dir)
        worker.file_copying.connect(self._on_file_copying)
        worker.log_message.connect(self._log)
        worker.finished.connect(self._on_import_done)
        self._workers.append(worker)
        worker.start()

    def _on_file_copying(self, filename: str, current: int, total: int):
        self._show_progress(f"{filename}", current, total)
        self.banner.show_progress(f"Importing {current}/{total}: {filename}")

    def _on_import_done(self, dest_paths: list):
        """Register imported files in DB (main thread — SQLite safe)."""
        self._hide_progress()
        self._log(f"Registering {len(dest_paths)} file(s) in database...")

        from db_builder.filetype import detect_source_type
        import hashlib

        registered = 0
        for path_str in dest_paths:
            try:
                dest = Path(path_str)
                if not dest.exists():
                    self._log(f"  SKIP (missing): {path_str}")
                    continue

                # Compute relative path safely
                try:
                    rel_str = str(dest.relative_to(self.raw_data_dir))
                except ValueError:
                    # Path not under raw_data_dir — use filename only
                    rel_str = dest.name

                size = dest.stat().st_size
                h = hashlib.md5()
                with open(dest, "rb") as f:
                    h.update(f.read(4096))
                h.update(str(size).encode())
                file_hash = h.hexdigest()
                stype = detect_source_type(dest)

                existing = self.db.get_file_by_path(rel_str)
                if existing is None:
                    self.db.insert_file(rel_str, file_hash, size, stype)
                    registered += 1
                elif existing["status"] != "pending":
                    # File exists but was processed — don't overwrite unless changed
                    if existing["file_hash"] != file_hash:
                        self.db.update_file_hash(existing["id"], file_hash, size)
                        self.db.update_file_status(existing["id"], "pending")
                        registered += 1
            except Exception as e:
                self._log(f"  ERROR registering {path_str}: {e}")

        self._log(f"Registered: {registered} new file(s)")
        self._set_busy(False)
        self._refresh_table()

        pending = len(self.db.list_files(status="pending"))
        if pending > 0:
            self.banner.show_info(f"{pending} file(s) ready to build", "Build Now")
            self.banner.btn_dismiss.show()
        elif dest_paths:
            self.banner.show_success("All files up to date")
        else:
            self.banner.hide()

    # ── Scan ──

    def _on_refresh(self):
        self._run_scan()

    def _run_scan(self):
        self._set_busy(True)
        self._show_progress("Scanning files...")

        scanner = FileScanner(self.raw_data_dir, self.db)
        worker = ScanWorker(scanner)
        worker.log_message.connect(self._log)
        worker.finished.connect(self._on_scan_done)
        self._workers.append(worker)
        worker.start()

    def _on_scan_done(self, results: list):
        self._hide_progress()
        self._set_busy(False)
        self._refresh_table()

        # Show banner if there are pending files
        pending = len(self.db.list_files(status="pending"))
        if pending > 0:
            self.banner.show_info(
                f"{pending} file(s) ready to build",
                "Build Now"
            )
            self.banner.btn_dismiss.show()
        elif results:
            self.banner.show_success("All files up to date")

    def _on_banner_build(self):
        self.banner.hide()
        self.request_build.emit()

    # ── Busy state ──

    def _set_busy(self, busy: bool):
        self.btn_add_folder.setEnabled(not busy)
        self.btn_add_files.setEnabled(not busy)
        self.btn_refresh.setEnabled(not busy)

    # ── Context menu ──

    def _on_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if item is not None:
            clicked_row = item.row()
            selected = set(idx.row() for idx in self.table.selectedIndexes())
            if clicked_row not in selected:
                self.table.selectRow(clicked_row)

        rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        if not rows or not self._row_file_ids:
            return

        file_ids = [self._row_file_ids[r] for r in rows if r < len(self._row_file_ids)]
        if not file_ids:
            return
        count = len(file_ids)

        menu = QMenu(self)

        if count == 1:
            fid = file_ids[0]
            f = self.db.get_file_by_id(fid)
            if f:
                if f["status"] == "failed" and f.get("error_message"):
                    err = f["error_message"]
                    menu.addAction("Show Error...", lambda _=False, e=err, p=f["file_path"]: self._action_show_error(p, e))
                if f["status"] in ("completed", "chunked", "embedded", "failed"):
                    menu.addAction("Rebuild", lambda _=False, ids=[fid]: self._action_rebuild(ids))
                path = f["file_path"]
                menu.addAction("Open in Explorer", lambda _=False, p=path: self._action_open_explorer(p))
                menu.addSeparator()

        menu.addAction(f"Reset to Pending ({count})", lambda _=False, ids=file_ids: self._action_reset(ids))
        menu.addSeparator()
        menu.addAction(f"Remove from List ({count})", lambda _=False, ids=file_ids: self._action_remove(ids))
        menu.addAction(f"Delete from Disk ({count})", lambda _=False, ids=file_ids: self._action_delete(ids))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _action_rebuild(self, ids):
        for fid in ids:
            self.db.delete_chunks_by_file(fid)
            self.db.update_file_status(fid, "pending")
        self._log(f"Reset {len(ids)} file(s) for rebuild")
        self._refresh_table()
        self.banner.show_info(f"{len(ids)} file(s) ready to rebuild", "Build Now")

    def _action_reset(self, ids):
        for fid in ids:
            self.db.update_file_status(fid, "pending")
        self._log(f"Reset {len(ids)} file(s) to pending")
        self._refresh_table()
        self.banner.show_info(f"{len(ids)} file(s) ready to build", "Build Now")

    def _action_remove(self, ids):
        if QMessageBox.question(
            self, "Remove", f"Remove {len(ids)} file(s) from list?\n(Disk files kept)",
        ) != QMessageBox.StandardButton.Yes:
            return
        for fid in ids:
            self.db.delete_chunks_by_file(fid)
            self.db.conn.execute("DELETE FROM files WHERE id = ?", (fid,))
        self.db.conn.commit()
        self._log(f"Removed {len(ids)} file(s)")
        self._refresh_table()

    def _action_delete(self, ids):
        if QMessageBox.warning(
            self, "Delete", f"Permanently delete {len(ids)} file(s) from disk?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        ) != QMessageBox.StandardButton.Yes:
            return
        for fid in ids:
            f = self.db.get_file_by_id(fid)
            if f:
                p = self.raw_data_dir / f["file_path"]
                if p.exists():
                    p.unlink()
            self.db.delete_chunks_by_file(fid)
            self.db.conn.execute("DELETE FROM files WHERE id = ?", (fid,))
        self.db.conn.commit()
        self._log(f"Deleted {len(ids)} file(s)")
        self._refresh_table()

    def _action_show_error(self, file_path: str, error: str):
        QMessageBox.warning(
            self, f"Error — {file_path}",
            f"File: {file_path}\n\nError:\n{error}",
        )

    def _action_open_explorer(self, file_path: str):
        full = self.raw_data_dir / file_path
        folder = full.parent if full.exists() else self.raw_data_dir
        os.startfile(str(folder))

    # ── Table ──

    def _refresh_table(self):
        files = self.db.list_files()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(files))
        self._row_file_ids = []

        for row, f in enumerate(files):
            self._row_file_ids.append(f["id"])
            status = f["status"]
            display, color = STATUS_DISPLAY.get(status, (status, "#888"))

            error_msg = f.get("error_message") or ""

            # Status cell — show error as tooltip + short indicator
            if status == "failed" and error_msg:
                display_text = f"Failed"
            else:
                display_text = display

            item_s = QTableWidgetItem(display_text)
            item_s.setForeground(QColor(color))
            font = item_s.font()
            font.setBold(True)
            item_s.setFont(font)
            if error_msg:
                item_s.setToolTip(f"Error: {error_msg}")
            self.table.setItem(row, 0, item_s)

            # File name — also show error tooltip on failed rows
            item_name = QTableWidgetItem(f["file_path"])
            if status == "failed" and error_msg:
                item_name.setToolTip(f"Error: {error_msg}")
                item_name.setForeground(QColor("#999"))
            self.table.setItem(row, 1, item_name)
            self.table.setItem(row, 2, QTableWidgetItem(
                TYPE_DISPLAY.get(f["source_type"], f["source_type"])
            ))

            size = f["file_size"]
            if size >= 1_048_576:
                s = f"{size/1_048_576:.1f} MB"
            elif size >= 1024:
                s = f"{size/1024:.1f} KB"
            else:
                s = f"{size} B"
            item_sz = QTableWidgetItem(s)
            item_sz.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, item_sz)

            chunks = f.get("chunk_count") or 0
            item_c = QTableWidgetItem(str(chunks) if chunks else "-")
            item_c.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, item_c)

            quality = f.get("avg_quality")
            if quality:
                item_q = QTableWidgetItem(f"{quality:.2f}")
                from db_builder.ui.theme import C_SUCCESS_TEXT, C_WARNING, C_ERROR
                c = C_SUCCESS_TEXT if quality >= 0.7 else C_WARNING if quality >= 0.5 else C_ERROR
                item_q.setForeground(QColor(c))
            else:
                item_q = QTableWidgetItem("-")
            item_q.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, item_q)

        self.table.setSortingEnabled(True)

        # Summary
        total = len(files)
        by_status = {}
        for f in files:
            by_status[f["status"]] = by_status.get(f["status"], 0) + 1
        parts = [f"Total: {total}"]
        for st, label in [("pending", "Pending"), ("completed", "Done"), ("failed", "Failed")]:
            if by_status.get(st):
                parts.append(f"{label}: {by_status[st]}")
        self.label_summary.setText("  |  ".join(parts))

    # ── Log ──

    def _log(self, msg: str):
        self.log_text.append(msg)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())
