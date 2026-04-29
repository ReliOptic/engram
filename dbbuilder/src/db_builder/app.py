"""PySide6 application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from db_builder.config import DBBuilderConfig
from db_builder.ui.main_window import MainWindow


def run_gui(config: DBBuilderConfig | None = None) -> int:
    """Launch the DB Builder GUI. Returns exit code."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName("Engram DB Builder")
    app.setApplicationVersion("0.1.0")

    from db_builder.ui.theme import GLOBAL_QSS
    app.setStyleSheet(GLOBAL_QSS)

    db_path = str(config.db_path) if config else ""
    chromadb_dir = str(config.chromadb_dir) if config else ""

    window = MainWindow(
        db_path=db_path,
        chromadb_dir=chromadb_dir,
        config=config,
    )
    window.show()

    return app.exec()
