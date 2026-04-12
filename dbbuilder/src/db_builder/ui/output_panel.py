"""Output panel — ChromaDB status, export, result overview."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db_builder.config import DBBuilderConfig
from db_builder.database import DatabaseManager
from db_builder.store.chromadb_writer import ChromaDBWriter


class OutputPanel(QWidget):
    """Shows what the build produced and where it lives."""

    def __init__(self, db: DatabaseManager, config: DBBuilderConfig, parent=None):
        super().__init__(parent)
        self.db = db
        self.config = config
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # ── Output Location ──
        loc_group = QGroupBox("Output Location")
        loc_layout = QFormLayout()

        self.label_chromadb_path = QLabel(str(self.config.chromadb_dir))
        self.label_chromadb_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.label_chromadb_path.setStyleSheet("font-family: monospace; color: #333;")
        loc_layout.addRow("ChromaDB directory:", self.label_chromadb_path)

        self.label_db_path = QLabel(str(self.config.db_path))
        self.label_db_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.label_db_path.setStyleSheet("font-family: monospace; color: #888;")
        loc_layout.addRow("State database:", self.label_db_path)

        btn_row = QHBoxLayout()
        self.btn_open_output = QPushButton("Open Output Folder")
        self.btn_open_output.clicked.connect(self._on_open_output)
        self.btn_export = QPushButton("Export ChromaDB to...")
        self.btn_export.setStyleSheet(
            "QPushButton{background:#FF9800;color:white;font-weight:bold;"
            "border-radius:4px;padding:6px 16px}"
            "QPushButton:hover{background:#F57C00}"
        )
        self.btn_export.clicked.connect(self._on_export)
        btn_row.addWidget(self.btn_open_output)
        btn_row.addWidget(self.btn_export)
        btn_row.addStretch()
        loc_layout.addRow("", btn_row)

        loc_group.setLayout(loc_layout)
        layout.addWidget(loc_group)

        # ── ChromaDB Collections ──
        col_group = QGroupBox("ChromaDB Collections")
        col_layout = QVBoxLayout()

        self.label_manuals = self._make_stat_row("manuals", "Type M — Manuals, SOPs, Error DB")
        self.label_weekly = self._make_stat_row("weekly", "Type C — Weekly Reports")

        col_layout.addLayout(self.label_manuals["layout"])
        col_layout.addLayout(self.label_weekly["layout"])
        col_group.setLayout(col_layout)
        layout.addWidget(col_group)

        # ── Build Summary ──
        summary_group = QGroupBox("Build Summary")
        summary_layout = QFormLayout()

        self.lbl_total_files = QLabel("-")
        self.lbl_total_chunks = QLabel("-")
        self.lbl_accepted = QLabel("-")
        self.lbl_quarantined = QLabel("-")
        self.lbl_embedded = QLabel("-")
        self.lbl_avg_quality = QLabel("-")
        self.lbl_disk_size = QLabel("-")

        summary_layout.addRow("Total files:", self.lbl_total_files)
        summary_layout.addRow("Total chunks:", self.lbl_total_chunks)
        summary_layout.addRow("Accepted:", self.lbl_accepted)
        summary_layout.addRow("Quarantined:", self.lbl_quarantined)
        summary_layout.addRow("Embedded:", self.lbl_embedded)
        summary_layout.addRow("Avg quality:", self.lbl_avg_quality)
        summary_layout.addRow("ChromaDB size:", self.lbl_disk_size)

        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)

        # ── Refresh ──
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh)
        layout.addWidget(btn_refresh, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

    def _make_stat_row(self, collection_name: str, description: str) -> dict:
        row = QHBoxLayout()
        name_lbl = QLabel(f"<b>{collection_name}</b>")
        name_lbl.setMinimumWidth(140)
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet("color: #888;")
        count_lbl = QLabel("0 chunks")
        count_lbl.setMinimumWidth(100)
        count_lbl.setStyleSheet("font-weight: bold; color: #333;")
        count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        row.addWidget(name_lbl)
        row.addWidget(desc_lbl, 1)
        row.addWidget(count_lbl)

        return {"layout": row, "count_label": count_lbl, "name": collection_name}

    def refresh(self):
        """Reload all stats from DB and ChromaDB."""
        # ChromaDB stats
        try:
            writer = ChromaDBWriter(self.config.chromadb_dir)
            for info in [self.label_manuals, self.label_weekly]:
                stats = writer.get_collection_stats(info["name"])
                info["count_label"].setText(f"{stats['count']} chunks")
        except Exception:
            for info in [self.label_manuals, self.label_weekly]:
                info["count_label"].setText("(unavailable)")

        # SQLite stats
        files = self.db.list_files()
        build_stats = self.db.get_build_stats()

        self.lbl_total_files.setText(str(len(files)))
        self.lbl_total_chunks.setText(str(build_stats.get("total_chunks", 0)))
        self.lbl_accepted.setText(str(build_stats.get("accepted") or 0))
        self.lbl_quarantined.setText(str(build_stats.get("quarantined") or 0))
        self.lbl_embedded.setText(str(build_stats.get("embedded") or 0))

        avg_q = build_stats.get("avg_quality")
        self.lbl_avg_quality.setText(f"{avg_q:.3f}" if avg_q else "-")

        # Disk size
        chroma_path = Path(self.config.chromadb_dir)
        if chroma_path.exists():
            total_bytes = sum(f.stat().st_size for f in chroma_path.rglob("*") if f.is_file())
            if total_bytes >= 1_048_576:
                self.lbl_disk_size.setText(f"{total_bytes / 1_048_576:.1f} MB")
            elif total_bytes >= 1024:
                self.lbl_disk_size.setText(f"{total_bytes / 1024:.1f} KB")
            else:
                self.lbl_disk_size.setText(f"{total_bytes} B")
        else:
            self.lbl_disk_size.setText("(not created yet)")

    def _on_open_output(self):
        path = Path(self.config.chromadb_dir)
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))

    def _on_export(self):
        dest = QFileDialog.getExistingDirectory(
            self, "Export ChromaDB To...", "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if not dest:
            return

        dest_path = Path(dest) / "chroma_db"
        if dest_path.exists():
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"{dest_path} already exists.\nOverwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            writer = ChromaDBWriter(self.config.chromadb_dir)
            writer.export(dest_path)
            QMessageBox.information(
                self, "Export Complete",
                f"ChromaDB exported to:\n{dest_path}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))
