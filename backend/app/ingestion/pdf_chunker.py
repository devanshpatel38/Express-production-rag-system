"""Turn loader PageContent into retrievable Chunks: prose windows, table rows, figures.

Every chunk's ``page`` is read from the enclosing ``PageContent.page`` (the
authoritative 1-based page number), never from TableData/FigureContent.
"""
from __future__ import annotations

import uuid

from app.ingestion.chunker import Chunk
from app.ingestion.pdf_loader import PageContent


def _prose_chunks(pc: PageContent, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Slide a window over the page prose, snapping breaks to paragraph boundaries."""
    text = pc.prose_text
    if not text.strip():
        return []
    label = f"Page {pc.page}"
    chunks: list[Chunk] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + chunk_size, n)
        # Try to extend to a paragraph break so we don't cut mid-sentence.
        if end < n:
            nl = text[end : min(end + 200, n)].find("\n\n")
            if nl != -1:
                end += nl
        snippet = text[i:end].strip()
        if snippet:
            chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid4()),
                    source_path="",
                    title=label,
                    section=label,
                    text=snippet,
                    char_start=i,
                    char_end=end,
                    page=pc.page,
                    chunk_type="prose",
                )
            )
        if end >= n:
            break
        i = max(end - chunk_overlap, i + 1)
    return chunks


def _table_chunks(pc: PageContent) -> list[Chunk]:
    chunks: list[Chunk] = []
    for td in pc.tables:
        header = f"[Table: {td.title} | units: {td.units} | page {pc.page}]"
        for label, cells in td.rows:
            body = f"{td.title} — {label} | " + " | ".join(
                f"{col}: {val}" for col, val in cells.items()
            )
            chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid4()),
                    source_path="",
                    title=td.title,
                    section=f"Page {pc.page}",
                    text=f"{header}\n{body}",
                    char_start=0,
                    char_end=0,
                    page=pc.page,
                    chunk_type="table_row",
                    table_title=td.title,
                    units=td.units,
                )
            )
    return chunks


def _figure_chunks(pc: PageContent) -> list[Chunk]:
    return [
        Chunk(
            chunk_id=str(uuid.uuid4()),
            source_path="",
            title=fig.caption,
            section=f"Page {pc.page}",
            text=f"[Figure: {fig.caption} | page {pc.page}] {fig.description}",
            char_start=0,
            char_end=0,
            page=pc.page,
            chunk_type="figure",
        )
        for fig in pc.figures
    ]


def chunk_pages(pages: list[PageContent], chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for pc in pages:
        chunks.extend(_prose_chunks(pc, chunk_size, chunk_overlap))
        chunks.extend(_table_chunks(pc))
        chunks.extend(_figure_chunks(pc))
    return chunks
