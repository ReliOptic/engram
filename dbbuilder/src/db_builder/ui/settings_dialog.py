"""Settings dialog — paths, embedding provider, processing config."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
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

from db_builder.config import DBBuilderConfig, PROVIDER_PRESETS
from db_builder.ui.theme import C_TEXT_MUTED, C_TEXT_2, C_BRAND


class PathSelector(QHBoxLayout):
    """Line edit + Browse button for folder selection."""

    def __init__(self, initial: str = "", dialog_title: str = "Select Folder"):
        super().__init__()
        self.dialog_title = dialog_title
        self.line_edit = QLineEdit(initial)
        self.line_edit.setMinimumWidth(350)
        btn = QPushButton("Browse…")
        btn.setMaximumWidth(90)
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
        self.setWindowTitle("Settings — Engram DB Builder")
        self.setMinimumWidth(580)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(self._build_paths_group())
        layout.addWidget(self._build_provider_group())
        layout.addWidget(self._build_processing_group())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Group builders ─────────────────────────────────────────────

    def _build_paths_group(self) -> QGroupBox:
        group = QGroupBox("Paths")
        form = QFormLayout()
        form.setSpacing(8)

        self.raw_dir = PathSelector(
            str(self.config.raw_data_dir), "Select Raw Data Directory"
        )
        form.addRow("Input (raw data):", self.raw_dir)

        self.chromadb_dir = PathSelector(
            str(self.config.chromadb_dir), "Select ChromaDB Output Directory"
        )
        form.addRow("Output (ChromaDB):", self.chromadb_dir)

        db_lbl = QLabel(str(self.config.db_path))
        db_lbl.setStyleSheet(f"color:{C_TEXT_MUTED};font-size:11px;")
        form.addRow("State DB:", db_lbl)

        group.setLayout(form)
        return group

    def _build_provider_group(self) -> QGroupBox:
        group = QGroupBox("Embedding Provider")
        form = QFormLayout()
        form.setSpacing(8)

        # Provider dropdown
        self.provider_combo = QComboBox()
        self._preset_keys: list[str] = []
        for key, preset in PROVIDER_PRESETS.items():
            self.provider_combo.addItem(preset["label"])
            self._preset_keys.append(key)

        # Determine current provider
        current_provider = os.getenv("DB_BUILDER_PROVIDER", "")
        if not current_provider and self.config.embedding:
            current_provider = self.config.embedding.provider
        idx = self._preset_keys.index(current_provider) if current_provider in self._preset_keys else 1
        self.provider_combo.setCurrentIndex(idx)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider:", self.provider_combo)

        # API Key
        self.api_key_label_widget = QLabel("API Key:")
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(self.api_key_label_widget, self.api_key_edit)

        # Base URL (editable override)
        self.base_url_edit = QLineEdit()
        form.addRow("Base URL:", self.base_url_edit)

        # Model (editable override)
        self.model_edit = QLineEdit()
        form.addRow("Embedding model:", self.model_edit)

        # Cost hint (read-only)
        self.cost_label = QLabel()
        self.cost_label.setStyleSheet(f"color:{C_TEXT_MUTED};font-size:11px;")
        form.addRow("Cost:", self.cost_label)

        group.setLayout(form)

        # Populate fields for the current provider
        self._on_provider_changed(idx)
        return group

    def _build_processing_group(self) -> QGroupBox:
        group = QGroupBox("Processing")
        form = QFormLayout()
        form.setSpacing(8)

        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(10, 500)
        self.batch_size_spin.setValue(self.config.embedding_batch_size)
        form.addRow("Embedding batch size:", self.batch_size_spin)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(0, 100)
        self.quality_spin.setValue(int(self.config.quality_threshold * 100))
        self.quality_spin.setSuffix("%")
        form.addRow("Quality threshold:", self.quality_spin)

        group.setLayout(form)
        return group

    # ── Provider selection ─────────────────────────────────────────

    def _on_provider_changed(self, idx: int):
        if idx < 0 or idx >= len(self._preset_keys):
            return
        key = self._preset_keys[idx]
        preset = PROVIDER_PRESETS[key]

        self.api_key_label_widget.setText(preset["api_key_label"] + ":")
        self.api_key_edit.setPlaceholderText(preset["api_key_placeholder"])
        self.api_key_edit.setReadOnly(not preset["api_key_env"])

        # Pre-fill existing key if set
        existing_key = os.getenv(preset["api_key_env"], "") if preset["api_key_env"] else ""
        self.api_key_edit.setText(existing_key if existing_key else "")

        # Override from env if previously customized
        base_url = os.getenv("DB_BUILDER_BASE_URL", "") or preset["base_url"]
        model = os.getenv("DB_BUILDER_MODEL", "") or preset["model"]
        # Only use env overrides if they match the current provider selection
        # (reset to preset defaults when switching providers)
        current_env_provider = os.getenv("DB_BUILDER_PROVIDER", "")
        if current_env_provider != key:
            base_url = preset["base_url"]
            model = preset["model"]

        self.base_url_edit.setText(base_url)
        self.model_edit.setText(model)

        dims = preset.get("dimensions", 1536)
        cost = preset["cost_per_million_input"]
        if cost == 0.0:
            cost_str = "Free (within quota)"
        else:
            cost_str = f"${cost:.3f} / 1M tokens"
        self.cost_label.setText(f"{cost_str}  ·  {dims}d embeddings")

    # ── Save ───────────────────────────────────────────────────────

    def _on_accept(self):
        raw = Path(self.raw_dir.path)
        if not raw.exists():
            QMessageBox.warning(self, "Invalid Path",
                                f"Input directory does not exist:\n{raw}")
            return

        chromadb = Path(self.chromadb_dir.path)
        chromadb.mkdir(parents=True, exist_ok=True)

        idx = self.provider_combo.currentIndex()
        provider_key = self._preset_keys[idx]
        preset = PROVIDER_PRESETS[provider_key]

        base_url = self.base_url_edit.text().strip()
        model = self.model_edit.text().strip()
        api_key = self.api_key_edit.text().strip()

        env_updates: dict[str, str] = {
            "DB_BUILDER_PROVIDER": provider_key,
            "DB_BUILDER_BASE_URL": base_url,
            "DB_BUILDER_MODEL": model,
        }
        if api_key and preset["api_key_env"]:
            env_updates[preset["api_key_env"]] = api_key

        self._save_env(env_updates)

        self.config.raw_data_dir = raw
        self.config.chromadb_dir = chromadb
        self.config.embedding_batch_size = self.batch_size_spin.value()
        self.config.quality_threshold = self.quality_spin.value() / 100.0

        self.accept()

    def _save_env(self, updates: dict[str, str]):
        from db_builder.config import _project_root
        env_path = _project_root() / ".env"
        lines: list[str] = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()

        for key, value in updates.items():
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}"
                    found = True
                    break
            if not found:
                lines.append(f"{key}={value}")
            os.environ[key] = value

        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
