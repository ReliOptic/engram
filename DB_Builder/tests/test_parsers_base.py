"""Tests for base parser interface and data structures."""

from __future__ import annotations

from pathlib import Path

import pytest

from db_builder.parsers.base import (
    BaseParser,
    ImageRef,
    ParsedSection,
    Table,
    get_parser_for_extension,
    get_parser_for_file,
    infer_source_type,
    list_supported_extensions,
    register_parser,
    _PARSER_REGISTRY,
)


class TestDataStructures:
    def test_table_fields(self):
        t = Table(headers=["A", "B"], rows=[["1", "2"]], page_number=5, caption="Table 1")
        assert t.headers == ["A", "B"]
        assert t.rows == [["1", "2"]]
        assert t.page_number == 5
        assert t.caption == "Table 1"

    def test_table_defaults(self):
        t = Table(headers=[], rows=[])
        assert t.page_number is None
        assert t.caption is None

    def test_image_ref_fields(self):
        img = ImageRef(page_number=3, bbox=(0, 0, 100, 200), caption="Fig 1", ocr_text="hello")
        assert img.page_number == 3
        assert img.bbox == (0, 0, 100, 200)

    def test_image_ref_defaults(self):
        img = ImageRef()
        assert img.page_number is None
        assert img.bbox is None
        assert img.caption is None
        assert img.ocr_text is None

    def test_parsed_section_fields(self):
        s = ParsedSection(
            text="Chapter 8 content",
            section_path=["Chapter 8", "8.3 TIS Recal"],
            page_range=(41, 45),
            tables=[Table(headers=["X"], rows=[["1"]])],
            cross_refs=["Chapter 4.2"],
            language="mixed",
            metadata={"version": "SW 5.6.2"},
        )
        assert s.text == "Chapter 8 content"
        assert s.section_path == ["Chapter 8", "8.3 TIS Recal"]
        assert s.page_range == (41, 45)
        assert len(s.tables) == 1
        assert s.cross_refs == ["Chapter 4.2"]
        assert s.language == "mixed"
        assert s.metadata["version"] == "SW 5.6.2"

    def test_parsed_section_defaults(self):
        s = ParsedSection(text="hello")
        assert s.section_path == []
        assert s.page_range is None
        assert s.sheet_name is None
        assert s.tables == []
        assert s.images == []
        assert s.cross_refs == []
        assert s.language == "en"
        assert s.metadata == {}


class TestBaseParserABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseParser()  # type: ignore[abstract]

    def test_concrete_subclass_works(self):
        class DummyParser(BaseParser):
            def parse(self, file_path: Path) -> list[ParsedSection]:
                return [ParsedSection(text="dummy")]

            def supported_extensions(self) -> list[str]:
                return [".dummy"]

        p = DummyParser()
        result = p.parse(Path("test.dummy"))
        assert len(result) == 1
        assert result[0].text == "dummy"
        assert p.supported_extensions() == [".dummy"]


class TestParserRegistry:
    def setup_method(self):
        """Save and restore registry state."""
        self._saved = dict(_PARSER_REGISTRY)

    def teardown_method(self):
        _PARSER_REGISTRY.clear()
        _PARSER_REGISTRY.update(self._saved)

    def test_register_and_lookup(self):
        class FakeParser(BaseParser):
            def parse(self, file_path): return []
            def supported_extensions(self): return [".fake"]

        register_parser([".fake", ".fk"], FakeParser)
        assert get_parser_for_extension(".fake") is FakeParser
        assert get_parser_for_extension(".fk") is FakeParser

    def test_case_insensitive(self):
        class FakeParser(BaseParser):
            def parse(self, file_path): return []
            def supported_extensions(self): return [".test"]

        register_parser([".TEST"], FakeParser)
        assert get_parser_for_extension(".test") is FakeParser

    def test_unknown_extension_returns_none(self):
        assert get_parser_for_extension(".xyz123") is None

    def test_get_parser_for_file(self):
        class FakeParser(BaseParser):
            def parse(self, file_path): return []
            def supported_extensions(self): return [".fp"]

        register_parser([".fp"], FakeParser)
        parser = get_parser_for_file(Path("test.fp"))
        assert parser is not None
        assert isinstance(parser, FakeParser)

    def test_get_parser_for_unknown_file(self):
        assert get_parser_for_file(Path("test.unknown999")) is None


class TestSourceTypeInference:
    @pytest.mark.parametrize("filename,expected", [
        # Extension-based (no folder context)
        ("manual.pdf", "manual"),
        ("report.xlsx", "weekly"),
        ("report.xls", "weekly"),
        ("procedure.docx", "sop"),
        ("photo.png", "image"),
        ("photo.jpg", "image"),
        ("photo.jpeg", "image"),
        ("scan.tiff", "image"),
        ("scan.bmp", "image"),
        ("notes.md", "misc"),
        ("log.txt", "misc"),
        ("data.csv", "misc"),
        ("unknown.xyz", "misc"),
    ])
    def test_infer_from_extension(self, filename: str, expected: str):
        assert infer_source_type(Path(filename)) == expected

    @pytest.mark.parametrize("filepath,expected", [
        # Folder override takes priority
        ("manuals/notes.md", "manual"),
        ("manuals/readme.txt", "manual"),
        ("manuals/PROVE_v3.pdf", "manual"),
        ("weekly_reports/CW15.xlsx", "weekly"),
        ("sops/procedure.txt", "sop"),
        ("images/diagram.pdf", "image"),
        ("error_db/codes.xlsx", "error_db"),
        ("cal_log/data.csv", "cal_log"),
        ("calibration/params.txt", "cal_log"),
        # Nested folders
        ("data/raw/manuals/subfolder/doc.md", "manual"),
        # No matching folder → fallback to extension
        ("misc/notes.md", "misc"),
        ("other/file.pdf", "manual"),
    ])
    def test_infer_from_folder(self, filepath: str, expected: str):
        assert infer_source_type(Path(filepath)) == expected
