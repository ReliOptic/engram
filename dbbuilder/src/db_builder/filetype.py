"""File type detection using magic bytes + extension fallback.

Detects actual file content type regardless of extension.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Magic bytes signatures (checked before python-magic as fast path)
_MAGIC_SIGS: list[tuple[bytes, int, str]] = [
    (b"%PDF",         0, "application/pdf"),
    (b"PK\x03\x04",  0, "application/zip"),       # xlsx/docx are ZIP-based
    (b"\x89PNG",      0, "image/png"),
    (b"\xff\xd8\xff", 0, "image/jpeg"),
    (b"GIF87a",       0, "image/gif"),
    (b"GIF89a",       0, "image/gif"),
    (b"II\x2a\x00",   0, "image/tiff"),            # little-endian TIFF
    (b"MM\x00\x2a",   0, "image/tiff"),            # big-endian TIFF
    (b"BM",           0, "image/bmp"),
]

# MIME → our source_type mapping
MIME_TO_SOURCE: dict[str, str] = {
    "application/pdf":   "manual",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "weekly",
    "application/vnd.ms-excel": "weekly",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "sop",
    "application/msword": "sop",
    "image/png":   "image",
    "image/jpeg":  "image",
    "image/tiff":  "image",
    "image/bmp":   "image",
    "image/gif":   "image",
    "text/plain":  "misc",
    "text/markdown": "misc",
    "text/csv":    "misc",
}

# Extension fallback for when MIME is ambiguous
EXT_TO_SOURCE: dict[str, str] = {
    ".pdf": "manual", ".xlsx": "weekly", ".xls": "weekly",
    ".docx": "sop", ".doc": "sop",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".tiff": "image", ".bmp": "image",
    ".md": "misc", ".txt": "misc", ".csv": "misc",
}

# ZIP-based formats: need extension to distinguish xlsx vs docx
_ZIP_EXT_MAP: dict[str, str] = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls":  "application/vnd.ms-excel",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

# All extensions we support
SUPPORTED_EXTENSIONS = set(EXT_TO_SOURCE.keys())


def detect_mime(file_path: Path) -> str:
    """Detect MIME type from file content.

    Strategy:
    1. Fast check: magic bytes signatures
    2. If ZIP-based: use extension to disambiguate xlsx/docx
    3. Fallback: python-magic library
    4. Last resort: extension-based guess
    """
    # 1. Magic bytes (fast, no external deps)
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
    except OSError:
        return _guess_from_extension(file_path)

    if not header:
        return "application/octet-stream"

    for sig, offset, mime in _MAGIC_SIGS:
        if header[offset:offset + len(sig)] == sig:
            # ZIP-based: need extension to tell xlsx from docx
            if mime == "application/zip":
                ext = file_path.suffix.lower()
                if ext in _ZIP_EXT_MAP:
                    return _ZIP_EXT_MAP[ext]
                # Try to peek inside ZIP for content type
                return _detect_zip_content(file_path, ext)
            return mime

    # 2. python-magic (more thorough)
    try:
        import magic
        mime = magic.from_file(str(file_path), mime=True)
        if mime and mime != "application/octet-stream":
            return mime
    except Exception:
        pass

    # 3. Extension fallback
    return _guess_from_extension(file_path)


def _detect_zip_content(file_path: Path, ext: str) -> str:
    """Peek inside a ZIP to determine if it's xlsx, docx, etc."""
    import zipfile
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()
            if any("xl/" in n or "xl\\" in n for n in names):
                return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if any("word/" in n or "word\\" in n for n in names):
                return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if any("ppt/" in n or "ppt\\" in n for n in names):
                return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    except Exception:
        pass
    return "application/zip"


def _guess_from_extension(file_path: Path) -> str:
    """Last resort: guess MIME from extension."""
    ext = file_path.suffix.lower()
    ext_map = {
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".tiff": "image/tiff", ".bmp": "image/bmp",
        ".md": "text/markdown", ".txt": "text/plain", ".csv": "text/csv",
    }
    return ext_map.get(ext, "application/octet-stream")


def detect_source_type(file_path: Path) -> str:
    """Detect source type from file content + folder context.

    Returns: manual, weekly, sop, error_db, cal_log, image, misc
    """
    # Folder-based override (highest priority)
    from db_builder.parsers.base import FOLDER_TYPE_MAP
    for part in file_path.parts[:-1]:
        ft = FOLDER_TYPE_MAP.get(part.lower())
        if ft:
            return ft

    # MIME-based detection
    mime = detect_mime(file_path)
    source = MIME_TO_SOURCE.get(mime)
    if source:
        return source

    # Extension fallback
    return EXT_TO_SOURCE.get(file_path.suffix.lower(), "misc")


def is_supported(file_path: Path) -> bool:
    """Check if a file is supported (by extension or content)."""
    if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
        return True
    # Try content-based detection
    mime = detect_mime(file_path)
    return mime in MIME_TO_SOURCE


def get_file_info(file_path: Path) -> dict:
    """Get comprehensive file type info."""
    mime = detect_mime(file_path)
    source_type = detect_source_type(file_path)
    return {
        "mime": mime,
        "source_type": source_type,
        "extension": file_path.suffix.lower(),
        "size": file_path.stat().st_size if file_path.exists() else 0,
    }
