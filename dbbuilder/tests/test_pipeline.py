"""Tests for pipeline file scanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from db_builder.database import DatabaseManager
from db_builder.pipeline import FileScanner, compute_file_hash


@pytest.fixture
def db(sample_db_path: Path) -> DatabaseManager:
    manager = DatabaseManager(sample_db_path)
    manager.init_schema()
    yield manager
    manager.close()


@pytest.fixture
def raw_dir(tmp_data_dir: Path) -> Path:
    """Raw data dir with sample files."""
    d = tmp_data_dir / "raw"
    # Create sample files
    (d / "manuals" / "sample_manual.pdf").write_bytes(b"%PDF-1.4 fake pdf content")
    (d / "weekly_reports" / "CW15_Weekly.xlsx").write_bytes(b"PK\x03\x04 fake xlsx")
    (d / "sops" / "PM_Procedure.docx").write_bytes(b"PK\x03\x04 fake docx")
    (d / "misc" / "notes.md").write_text("# Notes\nSome notes here.")
    (d / "misc" / "readme.txt").write_text("Just a text file.")
    return d


class TestComputeFileHash:
    def test_deterministic(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h1 = compute_file_hash(f)
        h2 = compute_file_hash(f)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_content_different_hash(self, tmp_path: Path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content A")
        f2.write_text("content B")
        assert compute_file_hash(f1) != compute_file_hash(f2)


class TestFileScanner:
    def test_discovers_supported_files(self, raw_dir: Path, db: DatabaseManager):
        scanner = FileScanner(raw_dir, db)
        results = scanner.scan()
        # Should find: .pdf, .xlsx, .docx, .md, .txt = 5 files
        assert len(results) == 5
        paths = {r["file_path"] for r in results}
        assert "manuals/sample_manual.pdf" in paths
        assert "weekly_reports/CW15_Weekly.xlsx" in paths
        assert "sops/PM_Procedure.docx" in paths
        assert "misc/notes.md" in paths
        assert "misc/readme.txt" in paths

    def test_skips_unsupported_files(self, raw_dir: Path, db: DatabaseManager):
        (raw_dir / "misc" / "binary.exe").write_bytes(b"\x00\x01\x02")
        (raw_dir / "misc" / "archive.zip").write_bytes(b"PK\x03\x04")
        scanner = FileScanner(raw_dir, db)
        results = scanner.scan()
        paths = {r["file_path"] for r in results}
        assert "misc/binary.exe" not in paths
        assert "misc/archive.zip" not in paths

    def test_registers_in_db(self, raw_dir: Path, db: DatabaseManager):
        scanner = FileScanner(raw_dir, db)
        scanner.scan()
        all_files = db.list_files()
        assert len(all_files) == 5
        for f in all_files:
            assert f["status"] == "pending"
            assert f["file_hash"] != ""
            assert f["file_size"] > 0

    def test_correct_source_types(self, raw_dir: Path, db: DatabaseManager):
        scanner = FileScanner(raw_dir, db)
        scanner.scan()
        pdf = db.get_file_by_path("manuals/sample_manual.pdf")
        assert pdf["source_type"] == "manual"
        xlsx = db.get_file_by_path("weekly_reports/CW15_Weekly.xlsx")
        assert xlsx["source_type"] == "weekly"
        docx = db.get_file_by_path("sops/PM_Procedure.docx")
        assert docx["source_type"] == "sop"

    def test_skips_unchanged_files(self, raw_dir: Path, db: DatabaseManager):
        scanner = FileScanner(raw_dir, db)
        first = scanner.scan()
        assert len(first) == 5

        # Second scan — same files, nothing changed
        second = scanner.scan()
        assert len(second) == 0

    def test_detects_changed_files(self, raw_dir: Path, db: DatabaseManager):
        scanner = FileScanner(raw_dir, db)
        scanner.scan()

        # Modify one file
        (raw_dir / "manuals" / "sample_manual.pdf").write_bytes(b"%PDF-1.4 UPDATED content")
        second = scanner.scan()
        assert len(second) == 1
        assert second[0]["file_path"] == "manuals/sample_manual.pdf"
        assert second[0]["status"] == "pending"

    def test_changed_file_clears_old_chunks(self, raw_dir: Path, db: DatabaseManager):
        scanner = FileScanner(raw_dir, db)
        scanner.scan()
        pdf = db.get_file_by_path("manuals/sample_manual.pdf")
        # Simulate existing chunks
        db.insert_chunk({
            "id": "old-chunk-1", "file_id": pdf["id"], "text": "old",
            "token_count": 10, "chunk_type": "manual",
            "source_file": "sample_manual.pdf", "source_type": "manual",
            "silo_key": "", "language": "en",
        })
        assert len(db.get_chunks_by_file(pdf["id"])) == 1

        # Change file
        (raw_dir / "manuals" / "sample_manual.pdf").write_bytes(b"NEW CONTENT")
        scanner.scan()
        assert len(db.get_chunks_by_file(pdf["id"])) == 0

    def test_handles_nonexistent_dir(self, sample_db_path: Path):
        db = DatabaseManager(sample_db_path)
        db.init_schema()
        scanner = FileScanner(Path("/nonexistent/dir"), db)
        results = scanner.scan()
        assert results == []
        db.close()

    def test_get_processable_files(self, raw_dir: Path, db: DatabaseManager):
        scanner = FileScanner(raw_dir, db)
        scanner.scan()
        pending = scanner.get_processable_files()
        assert len(pending) == 5
        # Mark one as completed
        db.update_file_status(pending[0]["id"], "completed")
        assert len(scanner.get_processable_files()) == 4

    def test_image_files_discovered(self, raw_dir: Path, db: DatabaseManager):
        (raw_dir / "images").mkdir(exist_ok=True)
        (raw_dir / "images" / "scan.png").write_bytes(b"\x89PNG fake")
        (raw_dir / "images" / "photo.jpg").write_bytes(b"\xff\xd8\xff fake jpg")
        scanner = FileScanner(raw_dir, db)
        results = scanner.scan()
        paths = {r["file_path"] for r in results}
        assert "images/scan.png" in paths
        assert "images/photo.jpg" in paths
        png = db.get_file_by_path("images/scan.png")
        assert png["source_type"] == "image"
