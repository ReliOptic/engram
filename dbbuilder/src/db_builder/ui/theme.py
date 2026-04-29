"""Engram design token system for DB Builder.

Mirrors the web app's CSS custom properties so both surfaces share
a consistent visual identity. Apply GLOBAL_QSS once via
QApplication.setStyleSheet(GLOBAL_QSS).
"""

from __future__ import annotations

# ── Brand ──────────────────────────────────────────────────────────
C_BRAND            = "#141E8C"
C_BRAND_LIGHT      = "#1A2BA8"
C_BRAND_LINK       = "#0072EF"

# ── Agents ─────────────────────────────────────────────────────────
C_ANALYZER         = "#2563EB"
C_FINDER           = "#0EA5A5"
C_REVIEWER         = "#6E5EFF"

# ── Semantic ───────────────────────────────────────────────────────
C_SUCCESS          = "#3AD2A3"
C_SUCCESS_SOFT     = "#E8FBF3"
C_SUCCESS_TEXT     = "#066149"
C_SUCCESS_EDGE     = "#A5D6A7"

C_ERROR            = "#E71E1E"
C_ERROR_SOFT       = "#FDECEC"
C_ERROR_TEXT       = "#92140C"
C_ERROR_EDGE       = "#F44336"

C_WARNING          = "#F5A623"
C_WARNING_SOFT     = "#FEF4E2"
C_WARNING_TEXT     = "#8C5A00"
C_WARNING_EDGE     = "#FFE0B2"

C_INFO_SOFT        = "#EAF1FF"
C_INFO_TEXT        = "#1D4ED8"

# ── Surfaces ───────────────────────────────────────────────────────
C_APP              = "#F4F4F2"
C_PANEL            = "#FFFFFF"
C_SUNKEN           = "#F8F8F6"
C_HOVER            = "#ECECE8"
C_PRESSED          = "#E1E1DC"

# ── Borders ────────────────────────────────────────────────────────
C_HAIR             = "#E6E6E1"
C_BORDER           = "#DCDCD6"
C_BORDER_MED       = "#CDCDC6"

# ── Text ───────────────────────────────────────────────────────────
C_TEXT             = "#14161A"
C_TEXT_2           = "#4B5159"
C_TEXT_MUTED       = "#7B828B"
C_TEXT_FAINT       = "#A6ABB2"

# ── Terminal (log/console areas) ───────────────────────────────────
C_TERM_BG          = "#0E1014"
C_TERM_FG          = "#B7BDCB"

# ── Status display for file processing pipeline ────────────────────
STATUS_DISPLAY: dict[str, tuple[str, str]] = {
    "pending":   ("Pending",   C_WARNING),
    "parsing":   ("Parsing…",  C_ANALYZER),
    "parsed":    ("Parsed",    C_ANALYZER),
    "chunked":   ("Chunked",   C_FINDER),
    "embedded":  ("Embedded",  C_FINDER),
    "completed": ("Done",      C_SUCCESS_TEXT),
    "failed":    ("Failed",    C_ERROR),
}

# ── Button QSS helpers ─────────────────────────────────────────────

def btn_filled(bg: str, hover: str, fg: str = "#FFFFFF") -> str:
    """Filled (primary-action) button style."""
    return (
        f"QPushButton{{background:{bg};color:{fg};font-weight:700;"
        f"border:none;border-radius:6px;padding:6px 22px;font-size:12px}}"
        f"QPushButton:hover{{background:{hover}}}"
        f"QPushButton:disabled{{background:{C_HOVER};color:{C_TEXT_FAINT};"
        f"border:1px solid {C_HAIR}}}"
    )


S_PRIMARY = btn_filled(C_BRAND,        C_BRAND_LIGHT)
S_START   = btn_filled(C_SUCCESS_TEXT, "#0A7A57")
S_PAUSE   = btn_filled(C_WARNING,      "#E09210", fg=C_TEXT)
S_RESUME  = btn_filled(C_ANALYZER,     "#1D4ED8")
S_STOP    = btn_filled(C_ERROR,        "#C41A1A")
S_EXPORT  = btn_filled(C_BRAND_LINK,   "#005EC4")

# ── Log / terminal widget QSS (applied per-widget) ─────────────────
LOG_QSS = (
    f"QTextEdit{{background:{C_TERM_BG};color:{C_TERM_FG};"
    f"border:1px solid {C_HAIR};border-radius:6px;"
    f"font-family:'JetBrains Mono','Consolas','Courier New',monospace;"
    f"font-size:11px;padding:4px}}"
)

# ── Global application stylesheet ─────────────────────────────────
GLOBAL_QSS = f"""
QWidget {{
    font-family: 'Space Grotesk', -apple-system, 'Segoe UI', Roboto, sans-serif;
    font-size: 13px;
    color: {C_TEXT};
    background-color: {C_APP};
}}
QMainWindow, QDialog {{
    background-color: {C_APP};
}}

/* Menu */
QMenuBar {{
    background: {C_APP};
    border-bottom: 1px solid {C_HAIR};
    padding: 2px 4px;
    spacing: 2px;
}}
QMenuBar::item {{
    padding: 4px 10px;
    background: transparent;
    border-radius: 4px;
    color: {C_TEXT_2};
    font-size: 12px;
}}
QMenuBar::item:selected {{ background: {C_HOVER}; color: {C_TEXT}; }}
QMenu {{
    background: {C_PANEL};
    border: 1px solid {C_BORDER};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 16px;
    border-radius: 4px;
    font-size: 12px;
    color: {C_TEXT_2};
}}
QMenu::item:selected {{ background: {C_INFO_SOFT}; color: {C_BRAND}; }}
QMenu::separator {{ height: 1px; background: {C_HAIR}; margin: 4px 8px; }}

/* Tabs */
QTabWidget::pane {{
    border: 1px solid {C_HAIR};
    border-top: none;
    background: {C_PANEL};
}}
QTabBar::tab {{
    background: {C_APP};
    border: 1px solid {C_HAIR};
    border-bottom: none;
    padding: 7px 18px;
    margin-right: 2px;
    font-weight: 600;
    font-size: 12px;
    color: {C_TEXT_MUTED};
    border-radius: 6px 6px 0 0;
}}
QTabBar::tab:selected {{
    background: {C_PANEL};
    color: {C_BRAND};
    border-top: 2px solid {C_BRAND};
}}
QTabBar::tab:hover:!selected {{ background: {C_HOVER}; color: {C_TEXT_2}; }}

/* Group box */
QGroupBox {{
    border: 1px solid {C_HAIR};
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px 6px 6px 6px;
    background: {C_PANEL};
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: {C_TEXT_MUTED};
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}}

/* Tables */
QTableWidget {{
    gridline-color: {C_HAIR};
    font-size: 12px;
    background-color: {C_PANEL};
    alternate-background-color: {C_SUNKEN};
    selection-background-color: {C_INFO_SOFT};
    selection-color: {C_TEXT};
    border: 1px solid {C_HAIR};
    border-radius: 6px;
}}
QTableWidget::item {{ padding: 4px 6px; }}
QHeaderView::section {{
    background: {C_APP};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid {C_HAIR};
    border-bottom: 1px solid {C_BORDER};
    font-weight: 700;
    font-size: 10px;
    color: {C_TEXT_MUTED};
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}

/* Progress */
QProgressBar {{
    border: 1px solid {C_BORDER};
    border-radius: 4px;
    background: {C_SUNKEN};
    text-align: center;
    font-size: 11px;
    color: {C_TEXT_2};
}}
QProgressBar::chunk {{
    background: {C_BRAND};
    border-radius: 3px;
}}

/* Buttons (default — no fill) */
QPushButton {{
    background: {C_PANEL};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 5px 14px;
    font-weight: 600;
    font-size: 12px;
    color: {C_TEXT_2};
}}
QPushButton:hover {{
    background: {C_HOVER};
    border-color: {C_BORDER_MED};
    color: {C_TEXT};
}}
QPushButton:pressed {{ background: {C_PRESSED}; }}
QPushButton:disabled {{
    background: {C_SUNKEN};
    color: {C_TEXT_FAINT};
    border-color: {C_HAIR};
}}

/* Inputs */
QLineEdit, QSpinBox, QComboBox {{
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    background: {C_PANEL};
    selection-background-color: {C_INFO_SOFT};
    font-size: 12px;
    color: {C_TEXT};
    min-height: 22px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {C_BRAND};
}}
QLineEdit:read-only {{
    background: {C_SUNKEN};
    color: {C_TEXT_2};
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {C_PANEL};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    selection-background-color: {C_INFO_SOFT};
    selection-color: {C_BRAND};
    font-size: 12px;
    padding: 2px;
}}

/* Status bar */
QStatusBar {{
    background: {C_APP};
    border-top: 1px solid {C_HAIR};
    font-size: 11px;
    color: {C_TEXT_MUTED};
}}

/* Scrollbars */
QScrollBar:vertical {{
    background: transparent; width: 10px; border: none;
}}
QScrollBar::handle:vertical {{
    background: {C_BORDER};
    border-radius: 5px;
    min-height: 20px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {C_BORDER_MED}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; border: none;
}}
QScrollBar::handle:horizontal {{
    background: {C_BORDER};
    border-radius: 5px;
    min-width: 20px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {C_BORDER_MED}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::corner {{ background: transparent; }}

/* Splitter */
QSplitter::handle {{ background: {C_HAIR}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

/* Tooltip */
QToolTip {{
    background: #14161A;
    color: #ECEEF3;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
}}

/* Checkbox */
QCheckBox {{ font-size: 12px; color: {C_TEXT_2}; spacing: 6px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {C_BORDER};
    border-radius: 3px;
    background: {C_PANEL};
}}
QCheckBox::indicator:checked {{
    background: {C_BRAND}; border-color: {C_BRAND};
}}

/* Text edit default (not log) */
QTextEdit {{
    border: 1px solid {C_HAIR};
    border-radius: 6px;
    background: {C_PANEL};
    font-size: 12px;
}}

/* Dialog button row */
QDialogButtonBox QPushButton {{ min-width: 80px; }}
"""
