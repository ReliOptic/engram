"""Weekly report ingester — parses Excel weekly reports into Type C chunks.

Handles two Excel formats:
- New format (CW09+): Proper columns (Cus. | FoB | Tool | Title | Status | Next Plan)
- Old format (CW52~CW08): Unnamed columns with merged cells

Spec reference: scaffolding-plan-v3.md Section 5.5, Section 12.6
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.knowledge.recording_policy import build_type_c_chunk

# New-format column mapping (CW09+)
NEW_FORMAT_COLS = {
    "Cus.": "account",
    "FoB": "fob",
    "Tool": "tool",
    "Title": "title",
    "Status": "status",
    "Next Plan": "next_plan",
}

# Old-format positional mapping (columns are Unnamed: 0..6)
OLD_FORMAT_POSITIONS = {
    0: "account",
    1: "fob",
    2: "tool",
    3: "title",
    4: "status",
    5: "next_plan",
}


class WeeklyIngester:
    """Parse Excel weekly reports into VectorDB chunks."""

    def __init__(self, xlsx_path: str):
        self._path = Path(xlsx_path)
        self._xl = pd.ExcelFile(self._path)

    @property
    def sheet_names(self) -> list[str]:
        return self._xl.sheet_names

    def parse_sheet(self, sheet_name: str) -> list[dict]:
        """Parse a single sheet into Type C chunks.

        Auto-detects format (new vs old) based on column names.
        """
        df = pd.read_excel(self._xl, sheet_name)

        if self._is_new_format(df):
            return self._parse_new_format(df, sheet_name)
        else:
            return self._parse_old_format(df, sheet_name)

    def parse_all_sheets(self) -> list[dict]:
        """Parse all sheets in the workbook."""
        all_chunks = []
        for sheet in self._xl.sheet_names:
            chunks = self.parse_sheet(sheet)
            all_chunks.extend(chunks)
        return all_chunks

    def _is_new_format(self, df: pd.DataFrame) -> bool:
        """Check if DataFrame has new-format column names."""
        cols = set(str(c) for c in df.columns)
        return "Cus." in cols or "Title" in cols

    def _parse_new_format(self, df: pd.DataFrame, sheet_name: str) -> list[dict]:
        """Parse new-format sheet (CW09+) with named columns."""
        chunks = []

        for _, row in df.iterrows():
            row_data = {"cw": sheet_name}

            for excel_col, field in NEW_FORMAT_COLS.items():
                val = row.get(excel_col, "")
                row_data[field] = str(val).strip() if pd.notna(val) else ""

            # Skip rows without meaningful content
            if not row_data.get("title") or row_data["title"] in ("", "nan"):
                continue

            chunk = build_type_c_chunk(row_data)
            chunks.append(chunk)

        return chunks

    def _parse_old_format(self, df: pd.DataFrame, sheet_name: str) -> list[dict]:
        """Parse old-format sheet (CW52~CW08) with unnamed/merged columns.

        Old format has metadata rows (dates, legends) mixed with data.
        We attempt best-effort extraction by skipping header-like rows.
        """
        chunks = []
        cols = list(df.columns)

        # Try to find data rows — skip rows that look like headers/metadata
        for idx, row in df.iterrows():
            vals = [str(row.iloc[i]).strip() if i < len(row) and pd.notna(row.iloc[i]) else ""
                    for i in range(min(7, len(cols)))]

            # Skip if first column looks like metadata (dates, "Reporting Part", etc.)
            first_val = vals[0] if vals else ""
            if not first_val or first_val in ("nan", "Reporting Part", "None Reporting Part"):
                continue
            if any(kw in first_val.lower() for kw in ["date", "legend", "week", "reporting"]):
                continue

            # Map positional columns to fields
            row_data = {"cw": sheet_name}
            for pos, field in OLD_FORMAT_POSITIONS.items():
                if pos < len(vals):
                    row_data[field] = vals[pos]

            # Must have at least a title to be useful
            title = row_data.get("title", "")
            if not title or title == "nan":
                continue

            chunk = build_type_c_chunk(row_data)
            chunks.append(chunk)

        return chunks
