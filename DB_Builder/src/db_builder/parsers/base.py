"""Base parser interface and shared data structures.

All parsers implement BaseParser and return list[ParsedSection].
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Table:
    """Extracted table from a document."""

    headers: list[str]
    rows: list[list[str]]
    page_number: int | None = None
    caption: str | None = None


@dataclass
class ImageRef:
    """Reference to an image in a document."""

    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    caption: str | None = None
    ocr_text: str | None = None


@dataclass
class ParsedSection:
    """Output unit from a parser. One logical section of a document."""

    text: str
    section_path: list[str] = field(default_factory=list)
    page_range: tuple[int, int] | None = None
    sheet_name: str | None = None
    tables: list[Table] = field(default_factory=list)
    images: list[ImageRef] = field(default_factory=list)
    cross_refs: list[str] = field(default_factory=list)
    language: str = "en"
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseParser(ABC):
    """Abstract base class for all document parsers."""

    @abstractmethod
    def parse(self, file_path: Path) -> list[ParsedSection]:
        """Parse a file into a list of sections."""
        ...

    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Return list of supported file extensions (e.g. ['.pdf'])."""
        ...


# Extension-to-parser-class mapping.
# Populated at import time by each parser module.
_PARSER_REGISTRY: dict[str, type[BaseParser]] = {}


def register_parser(extensions: list[str], parser_class: type[BaseParser]) -> None:
    """Register a parser class for the given file extensions."""
    for ext in extensions:
        _PARSER_REGISTRY[ext.lower()] = parser_class


def get_parser_for_extension(ext: str) -> type[BaseParser] | None:
    """Look up the parser class for a file extension."""
    return _PARSER_REGISTRY.get(ext.lower())


def get_parser_for_file(file_path: Path) -> BaseParser | None:
    """Instantiate the appropriate parser for a file."""
    ext = file_path.suffix.lower()
    parser_class = get_parser_for_extension(ext)
    if parser_class is None:
        return None
    return parser_class()


def list_supported_extensions() -> list[str]:
    """Return all registered file extensions."""
    return sorted(_PARSER_REGISTRY.keys())


# File extension → source_type mapping
SOURCE_TYPE_MAP: dict[str, str] = {
    ".pdf": "manual",
    ".xlsx": "weekly",
    ".xls": "weekly",
    ".docx": "sop",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tiff": "image",
    ".bmp": "image",
    ".md": "misc",
    ".txt": "misc",
    ".csv": "misc",
}


# Folder name → source_type override (takes priority over extension)
FOLDER_TYPE_MAP: dict[str, str] = {
    "manuals": "manual",
    "manual": "manual",
    "weekly_reports": "weekly",
    "weekly": "weekly",
    "sops": "sop",
    "sop": "sop",
    "images": "image",
    "image": "image",
    "error_db": "error_db",
    "cal_log": "cal_log",
    "calibration": "cal_log",
}


def infer_source_type(file_path: Path) -> str:
    """Infer source_type from folder name first, then file extension."""
    # Check parent folder names (walk up 2 levels)
    for parent in file_path.parts[:-1]:
        folder_type = FOLDER_TYPE_MAP.get(parent.lower())
        if folder_type:
            return folder_type
    return SOURCE_TYPE_MAP.get(file_path.suffix.lower(), "misc")
