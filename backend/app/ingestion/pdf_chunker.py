"""Chunker for loaded PDF documents: sliding-window prose + one chunk per table row.

The Chunk dataclass is a superset of the markdown chunker's (title, char_start,
char_end kept) so the indexer can consume it; Task 9 persists the new metadata.
Page numbers are 1-based and carried straight from the loader.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.ingestion.pdf_loader import LoadedDoc
from app.ingestion.pdf_tables import TableRecord, TableRow

CHUNK_SIZE = 700     # same as blueprint chunk_markdown
CHUNK_OVERLAP = 120  # same as blueprint chunk_markdown


@dataclass
class Chunk:
    chunk_id: str
    source_path: str
    title: str
    section: str
    text: str
    page: int
    chunk_type: str  # "prose" | "table_row"
    units: str | None = None
    table_title: str | None = None
    char_start: int = 0
    char_end: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _window(text: str, size: int, overlap: int) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    i, n = 0, len(text)
    while i < n:
        end = min(i + size, n)
        if end < n:
            nl = text[end : min(end + 200, n)].find("\n\n")
            if nl != -1:
                end += nl
        snippet = text[i:end].strip()
        if snippet:
            out.append((i, end, snippet))
        if end >= n:
            break
        i = max(end - overlap, i + 1)
    return out


def _render_row(table: TableRecord, row: TableRow) -> str:
    prefix = f"[Table: {table.title} | units: {table.units} | page {table.page}]"
    cells = "; ".join(f"{k}={v}" for k, v in row.values.items())
    return f"{prefix} {row.label}: {cells}"


def chunk_document(
    doc: LoadedDoc,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in doc.pages:
        section = page.section or f"Page {page.page}"
        idx = 0

        def next_id() -> str:
            nonlocal idx
            cid = f"{doc.source_path}:p{page.page}:{idx}"
            idx += 1
            return cid

        for start, end, snippet in _window(page.prose or "", chunk_size, chunk_overlap):
            chunks.append(Chunk(
                chunk_id=next_id(), source_path=doc.source_path, title=section,
                section=section, text=snippet, page=page.page, chunk_type="prose",
                char_start=start, char_end=end,
            ))
        for table in page.tables:
            for row in table.rows:
                text = _render_row(table, row)
                chunks.append(Chunk(
                    chunk_id=next_id(), source_path=doc.source_path, title=section,
                    section=section, text=text, page=table.page,
                    chunk_type="table_row", units=table.units,
                    table_title=table.title, char_start=0, char_end=len(text),
                ))
    return chunks
