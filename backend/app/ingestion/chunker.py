"""Chunk model and sliding-window text splitter shared by the ingestion pipeline."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str
    source_path: str
    title: str        # nearest heading / section title
    section: str      # section breadcrumb
    text: str
    char_start: int
    char_end: int
    page: int = 0                 # 1-based PDF page (0 = unknown)
    chunk_type: str = "prose"     # "prose" | "table_row"
    table_title: str = ""
    units: str = ""

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source_path": self.source_path,
            "title": self.title,
            "section": self.section,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "page": self.page,
            "chunk_type": self.chunk_type,
            "table_title": self.table_title,
            "units": self.units,
        }


def window_text(
    text: str, chunk_size: int, chunk_overlap: int
) -> list[tuple[int, int, str]]:
    """Slide a window over text, snapping breaks to paragraph boundaries when possible.

    Returns (char_start, char_end, stripped_snippet) tuples; empty snippets are skipped.
    """
    out: list[tuple[int, int, str]] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + chunk_size, n)
        # Try to extend to a paragraph break so we don't cut mid-sentence.
        if end < n:
            window = text[end : min(end + 200, n)]
            nl = window.find("\n\n")
            if nl != -1:
                end = end + nl

        snippet = text[i:end].strip()
        if snippet:
            out.append((i, end, snippet))
        if end >= n:
            break
        i = max(end - chunk_overlap, i + 1)
    return out
