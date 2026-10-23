"""Turn loader PageContent into retrievable Chunks (prose windows + one chunk per table row).

Every chunk's page is taken from PageContent.page (the single 1-based source of truth),
never from TableData.page.
"""
from __future__ import annotations

import uuid

from app.ingestion.chunker import Chunk, window_text
from app.ingestion.pdf_loader import PageContent


def _table_row_text(title: str, units: str, page: int, label: str, cells: dict[str, str]) -> str:
    header = f"[Table: {title} | units: {units} | page {page}]"
    body = f"{title} — {label} | " + " | ".join(f"{col}: {val}" for col, val in cells.items())
    return f"{header}\n{body}"


def chunk_pages(pages: list[PageContent], chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for pc in pages:
        section = pc.section or f"Page {pc.page}"
        source = f"page-{pc.page}"

        for start, end, snippet in window_text(pc.prose_text, chunk_size, chunk_overlap):
            chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid4()),
                    source_path=source,
                    title=section,
                    section=section,
                    text=snippet,
                    char_start=start,
                    char_end=end,
                    page=pc.page,
                    chunk_type="prose",
                )
            )

        for table in pc.tables:
            for label, cells in table.rows:
                text = _table_row_text(table.title, table.units, pc.page, label, cells)
                chunks.append(
                    Chunk(
                        chunk_id=str(uuid.uuid4()),
                        source_path=source,
                        title=table.title or section,
                        section=section,
                        text=text,
                        char_start=0,
                        char_end=len(text),
                        page=pc.page,
                        chunk_type="table_row",
                        table_title=table.title,
                        units=table.units,
                    )
                )
    return chunks
