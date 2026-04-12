"""PySide6 main window for DB Builder."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from db_builder.config import DBBuilderConfig
from db_builder.database import DatabaseManager


class PlaceholderTab(QWidget):
    """Placeholder widget for tabs not yet implemented."""

    def __init__(self, title: str, description: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #666;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc_label = QLabel(description)
        desc_label.setStyleSheet("font-size: 13px; color: #999;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title_label)
        layout.addWidget(desc_label)


class MainWindow(QMainWindow):
    """Main application window with file management and build pipeline."""

    def __init__(
        self,
        db_path: str = "",
        chromadb_dir: str = "",
        config: DBBuilderConfig | None = None,
    ):
        super().__init__()
        self.setWindowTitle("ZEMAS DB Builder")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)

        self._config = config
        self._db_path = db_path
        self._chromadb_dir = chromadb_dir

        # Initialize database
        self._db = DatabaseManager(db_path) if db_path else None
        if self._db:
            self._db.init_schema()

        self._setup_menu()
        self._setup_tabs()
        self._setup_statusbar()

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        file_menu.addAction("Settings...", self._on_settings)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self._on_about)

    def _setup_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        if self._db and self._config:
            from db_builder.ui.file_panel import FilePanel
            from db_builder.ui.build_panel import BuildPanel
            from db_builder.ui.output_panel import OutputPanel

            self.files_tab = FilePanel(
                db=self._db,
                raw_data_dir=self._config.raw_data_dir,
            )
            self.build_tab = BuildPanel(
                db=self._db,
                config=self._config,
            )
            self.output_tab = OutputPanel(
                db=self._db,
                config=self._config,
            )
            # Refresh panels when build finishes
            self.build_tab.build_finished.connect(self.files_tab._refresh_table)
            self.build_tab.build_finished.connect(self.output_tab.refresh)
            # "Build Now" from Files tab → switch to Build tab and start
            self.files_tab.request_build.connect(self._on_request_build)
        else:
            self.files_tab = PlaceholderTab("Files", "Database not configured.")
            self.build_tab = PlaceholderTab("Build", "Database not configured.")
            self.output_tab = PlaceholderTab("Output", "Database not configured.")

        self.inspector_tab = PlaceholderTab(
            "Inspector",
            "Chunk browser with quality breakdown.\n(Coming in Phase 5)"
        )

        self.tabs.addTab(self.files_tab, "Files")
        self.tabs.addTab(self.build_tab, "Build")
        self.tabs.addTab(self.output_tab, "Output")
        self.tabs.addTab(self.inspector_tab, "Inspector")

    def _setup_statusbar(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)

        left = QLabel(f"DB: {self._db_path}")
        left.setStyleSheet("color: #888; font-size: 11px;")
        right = QLabel(f"ChromaDB: {self._chromadb_dir}")
        right.setStyleSheet("color: #888; font-size: 11px;")

        status.addWidget(left, 1)
        status.addPermanentWidget(right)

    def _on_request_build(self) -> None:
        """Switch to Build tab and start building."""
        self.tabs.setCurrentWidget(self.build_tab)
        if hasattr(self.build_tab, '_on_main_clicked'):
            self.build_tab._on_main_clicked()

    def _on_settings(self) -> None:
        if not self._config:
            return
        from db_builder.ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self._config, self)
        if dlg.exec():
            # Config was updated — refresh statusbar
            self.statusBar().findChildren(QLabel)[0].setText(f"DB: {self._db_path}")
            chroma_lbl = self.statusBar().findChildren(QLabel)[-1]
            chroma_lbl.setText(f"ChromaDB: {self._config.chromadb_dir}")
            # Refresh output tab if it exists
            if hasattr(self, 'output_tab') and hasattr(self.output_tab, 'refresh'):
                self.output_tab.label_chromadb_path.setText(str(self._config.chromadb_dir))
                self.output_tab.refresh()

    def _on_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            "About ZEMAS DB Builder",
            "ZEMAS DB Builder v0.1.0\n\n"
            "Knowledge Base Construction Pipeline\n"
            "for ZEISS EUV Multi-Agent Support System.\n\n"
            "Author: Kiwon (ZEISS Korea)",
        )

    def closeEvent(self, event):
        if self._db:
            self._db.close()
        super().closeEvent(event)
