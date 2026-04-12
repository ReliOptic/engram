"""Settings dialog — paths, API key, embedding config."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from db_builder.config import DBBuilderConfig


class PathSelector(QHBoxLayout):
    """Line edit + Browse button for folder selection."""

    def __init__(self, initial: str = "", dialog_title: str = "Select Folder"):
        super().__init__()
        self.dialog_title = dialog_title
        self.line_edit = QLineEdit(initial)
        self.line_edit.setMinimumWidth(350)
        btn = QPushButton("Browse...")
        btn.setMaximumWidth(80)
        btn.clicked.connect(self._browse)
        self.addWidget(self.line_edit, 1)
        self.addWidget(btn)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            None, self.dialog_title, self.line_edit.text(),
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            self.line_edit.setText(folder)

    @property
    def path(self) -> str:
        return self.line_edit.text().strip()


class SettingsDialog(QDialog):
    """Application settings dialog."""

    def __init__(self, config: DBBuilderConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setMinimumWidth(550)

        layout = QVBoxLayout(self)

        # ── Paths ──
        paths_group = QGroupBox("Paths")
        paths_form = QFormLayout()

        self.raw_dir = PathSelector(
            str(config.raw_data_dir), "Select Raw Data Directory"
        )
        paths_form.addRow("Input (raw data):", self.raw_dir)

        self.chromadb_dir = PathSelector(
            str(config.chromadb_dir), "Select ChromaDB Output Directory"
        )
        paths_form.addRow("Output (ChromaDB):", self.chromadb_dir)

        self.db_path_label = QLabel(str(config.db_path))
        self.db_path_label.setStyleSheet("color: #888;")
        paths_form.addRow("State DB:", self.db_path_label)

        paths_group.setLayout(paths_form)
        layout.addWidget(paths_group)

        # ── API ──
        api_group = QGroupBox("Embedding API")
        api_form = QFormLayout()

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        current_key = os.getenv("OPENROUTER_API_KEY", "")
        if current_key:
            self.api_key_edit.setText(current_key)
            self.api_key_edit.setPlaceholderText("(key is set)")
        else:
            self.api_key_edit.setPlaceholderText("sk-or-v1-...")
        api_form.addRow("OpenRouter API Key:", self.api_key_edit)

        model_label = QLabel(config.embedding.model if config.embedding else "not configured")
        model_label.setStyleSheet("color: #888;")
        api_form.addRow("Embedding Model:", model_label)

        provider_label = QLabel(config.embedding.provider if config.embedding else "-")
        provider_label.setStyleSheet("color: #888;")
        api_form.addRow("Provider:", provider_label)

        cost_text = f"${config.embedding.cost_per_million_input:.3f} / 1M tokens" if config.embedding else "-"
        cost_label = QLabel(cost_text)
        cost_label.setStyleSheet("color: #888;")
        api_form.addRow("Cost:", cost_label)

        api_group.setLayout(api_form)
        layout.addWidget(api_group)

        # ── Processing ──
        proc_group = QGroupBox("Processing")
        proc_form = QFormLayout()

        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(10, 500)
        self.batch_size_spin.setValue(config.embedding_batch_size)
        proc_form.addRow("Embedding batch size:", self.batch_size_spin)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(0, 100)
        self.quality_spin.setValue(int(config.quality_threshold * 100))
        self.quality_spin.setSuffix("%")
        proc_form.addRow("Quality threshold:", self.quality_spin)

        proc_group.setLayout(proc_form)
        layout.addWidget(proc_group)

        # ── Buttons ──
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        # Validate paths
        raw = Path(self.raw_dir.path)
        if not raw.exists():
            QMessageBox.warning(self, "Invalid Path", f"Input directory does not exist:\n{raw}")
            return

        chromadb = Path(self.chromadb_dir.path)
        chromadb.mkdir(parents=True, exist_ok=True)

        # Save API key to .env if changed
        new_key = self.api_key_edit.text().strip()
        if new_key and new_key != os.getenv("OPENROUTER_API_KEY", ""):
            self._save_env_key(new_key)

        # Update config
        self.config.raw_data_dir = raw
        self.config.chromadb_dir = chromadb
        self.config.embedding_batch_size = self.batch_size_spin.value()
        self.config.quality_threshold = self.quality_spin.value() / 100.0

        self.accept()

    def _save_env_key(self, key: str):
        """Write API key to .env file."""
        from db_builder.config import _project_root
        env_path = _project_root() / ".env"
        lines = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()

        found = False
        for i, line in enumerate(lines):
            if line.startswith("OPENROUTER_API_KEY="):
                lines[i] = f"OPENROUTER_API_KEY={key}"
                found = True
                break
        if not found:
            lines.append(f"OPENROUTER_API_KEY={key}")

        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.environ["OPENROUTER_API_KEY"] = key
