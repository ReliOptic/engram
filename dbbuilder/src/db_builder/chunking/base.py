"""Chunking engine — splits parsed text into semantic chunks."""

from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tiktoken


@dataclass
class Chunk:
    """A single chunk ready for embedding."""

    id: str
    text: str
    token_count: int
    source_file: str
    source_type: str
    section_title: str = ""
    section_path: list[str] = field(default_factory=list)
    page_number: int | None = None
    sheet_name: str | None = None
    language: str = "en"
    metadata: dict[str, Any] = field(default_factory=dict)


# Shared tokenizer (cl100k_base = GPT-4/embedding model tokenizer)
_enc: tiktoken.Encoding | None = None


def count_tokens(text: str) -> int:
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding("cl100k_base")
    return len(_enc.encode(text))


def generate_chunk_id(source_file: str, location: str, index: int) -> str:
    """Deterministic chunk ID for rebuild safety."""
    fhash = hashlib.md5(source_file.encode()).hexdigest()[:6]
    loc = re.sub(r'[^a-zA-Z0-9_]', '', location)[:20]
    return f"m-{fhash}_{loc}_{index:03d}"


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences (handles EN/DE/KO)."""
    # Split on sentence boundaries: . ! ? followed by space/newline/EOF
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


class SemanticChunker:
    """Splits text into semantic chunks respecting sentence boundaries."""

    def __init__(
        self,
        max_tokens: int = 1024,
        min_tokens: int = 50,
        overlap_sentences: int = 2,
    ):
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.overlap_sentences = overlap_sentences

    def chunk_text(
        self,
        text: str,
        source_file: str,
        source_type: str = "manual",
        section_title: str = "",
        section_path: list[str] | None = None,
        page_number: int | None = None,
        base_location: str = "s00",
    ) -> list[Chunk]:
        """Split text into semantic chunks."""
        if not text.strip():
            return []

        sentences = split_into_sentences(text)
        if not sentences:
            # Still create a chunk from raw text if non-empty
            if text.strip():
                return [self._make_chunk(
                    [text.strip()], source_file, source_type,
                    section_title, section_path, page_number,
                    base_location, 0,
                )]
            return []

        chunks: list[Chunk] = []
        current: list[str] = []
        current_tokens = 0
        idx = 0

        for sent in sentences:
            sent_tokens = count_tokens(sent)

            # Single sentence exceeds max? Force as its own chunk
            if sent_tokens > self.max_tokens:
                if current:
                    chunks.append(self._make_chunk(
                        current, source_file, source_type,
                        section_title, section_path, page_number,
                        base_location, idx,
                    ))
                    idx += 1
                    current = []
                    current_tokens = 0

                chunks.append(self._make_chunk(
                    [sent], source_file, source_type,
                    section_title, section_path, page_number,
                    base_location, idx,
                ))
                idx += 1
                continue

            # Would adding this sentence exceed max?
            if current_tokens + sent_tokens > self.max_tokens and current:
                chunks.append(self._make_chunk(
                    current, source_file, source_type,
                    section_title, section_path, page_number,
                    base_location, idx,
                ))
                idx += 1
                # Overlap: keep last N sentences
                overlap = current[-self.overlap_sentences:] if self.overlap_sentences else []
                current = overlap
                current_tokens = sum(count_tokens(s) for s in current)

            current.append(sent)
            current_tokens += sent_tokens

        # Remaining
        if current:
            # Merge tiny last chunk with previous if possible
            if current_tokens < self.min_tokens and chunks:
                prev = chunks[-1]
                merged_text = prev.text + "\n" + " ".join(current)
                if count_tokens(merged_text) <= self.max_tokens * 1.2:
                    chunks[-1] = Chunk(
                        id=prev.id, text=merged_text,
                        token_count=count_tokens(merged_text),
                        source_file=prev.source_file,
                        source_type=prev.source_type,
                        section_title=prev.section_title,
                        section_path=prev.section_path or [],
                        page_number=prev.page_number,
                    )
                else:
                    chunks.append(self._make_chunk(
                        current, source_file, source_type,
                        section_title, section_path, page_number,
                        base_location, idx,
                    ))
            else:
                chunks.append(self._make_chunk(
                    current, source_file, source_type,
                    section_title, section_path, page_number,
                    base_location, idx,
                ))

        return chunks

    def _make_chunk(
        self, sentences, source_file, source_type,
        section_title, section_path, page_number,
        base_location, index,
    ) -> Chunk:
        text = " ".join(sentences)
        breadcrumb = ""
        if section_title:
            breadcrumb = f"[{section_title}]\n"

        full_text = breadcrumb + text
        return Chunk(
            id=generate_chunk_id(source_file, base_location, index),
            text=full_text,
            token_count=count_tokens(full_text),
            source_file=source_file,
            source_type=source_type,
            section_title=section_title,
            section_path=section_path or [],
            page_number=page_number,
        )


class MarkdownChunker:
    """Splits markdown by headings, then applies semantic chunking within sections."""

    def __init__(self, max_tokens: int = 1024, min_tokens: int = 50):
        self.semantic = SemanticChunker(max_tokens, min_tokens)

    def chunk_markdown(
        self,
        text: str,
        source_file: str,
        source_type: str = "manual",
    ) -> list[Chunk]:
        sections = self._split_by_headings(text)
        all_chunks: list[Chunk] = []

        for section_title, section_text, level in sections:
            location = re.sub(r'[^a-zA-Z0-9]', '', section_title)[:15] or "root"
            chunks = self.semantic.chunk_text(
                text=section_text,
                source_file=source_file,
                source_type=source_type,
                section_title=section_title,
                section_path=[section_title] if section_title else [],
                base_location=location,
            )
            all_chunks.extend(chunks)

        # Guarantee at least 1 chunk if there's any text at all
        if not all_chunks and text.strip():
            all_chunks.append(Chunk(
                id=generate_chunk_id(source_file, "full", 0),
                text=text.strip(),
                token_count=count_tokens(text.strip()),
                source_file=source_file,
                source_type=source_type,
            ))

        return all_chunks

    def _split_by_headings(self, text: str) -> list[tuple[str, str, int]]:
        """Split markdown into (title, body, level) tuples."""
        lines = text.split("\n")
        sections: list[tuple[str, str, int]] = []
        current_title = ""
        current_lines: list[str] = []
        current_level = 0

        for line in lines:
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                # Save previous section
                if current_lines or current_title:
                    body = "\n".join(current_lines).strip()
                    # Include section even if body is empty (title-only)
                    if body or current_title:
                        sections.append((current_title, body or current_title, current_level))

                current_level = len(heading_match.group(1))
                current_title = heading_match.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)

        # Last section
        body = "\n".join(current_lines).strip()
        if body:
            sections.append((current_title, body, current_level))

        return sections
