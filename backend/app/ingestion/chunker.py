"""Chunk data model shared by the ingestion pipeline.

PDF chunk construction lives in ``app.ingestion.pdf_chunker``.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str
    source_path: str
    title: str        # nearest heading
    section: str      # full breadcrumb e.g. "Guide > Routing > Route paths"
    text: str
    char_start: int
    char_end: int
    page: int = 0               # 1-based PDF page number
    chunk_type: str = "prose"   # "prose" | "table_row" | "figure"
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
