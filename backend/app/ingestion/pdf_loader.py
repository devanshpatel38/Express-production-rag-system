"""Orchestrates the PDF ingestion modules into clean per-page prose + tables.

Step order (per document):
  1. per page: extract_blocks -> extract_tables -> drop blocks inside table
     bboxes -> order_blocks -> join with blank-line-free newlines.
  2. strip_running_headers ONCE over all raw page texts (header lines are
     detected by digit-masked exact match, so this runs BEFORE normalisation
     which could alter header characters).
  3. normalize_text each cleaned page.

Table-subtraction rule: a block is dropped if its centre lies inside any
validated table bbox, or if >50% of its area overlaps one.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import pymupdf

from app.config import get_settings
from app.ingestion.pdf_layout import order_blocks
from app.ingestion.pdf_spans import Block, extract_blocks
from app.ingestion.pdf_tables import TableRecord, extract_tables
from app.ingestion.pdf_text import normalize_text, strip_running_headers


@dataclass
class LoadedPage:
    page: int  # 1-based
    section: str
    prose: str
    tables: list[TableRecord] = field(default_factory=list)


@dataclass
class LoadedDoc:
    source_path: str  # PDF basename
    pages: list[LoadedPage] = field(default_factory=list)


def _in_table(block: Block, bboxes: list[tuple[float, float, float, float]]) -> bool:
    cx, cy = (block.x0 + block.x1) / 2, (block.y0 + block.y1) / 2
    area = max((block.x1 - block.x0) * (block.y1 - block.y0), 1e-6)
    for x0, y0, x1, y1 in bboxes:
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return True
        w = min(block.x1, x1) - max(block.x0, x0)
        h = min(block.y1, y1) - max(block.y0, y0)
        if w > 0 and h > 0 and (w * h) / area > 0.5:
            return True
    return False


def load_pdf(path: str | None = None) -> LoadedDoc:
    path = path or get_settings().source_pdf_path
    raw_texts: list[str] = []
    tables_by_page: list[list[TableRecord]] = []
    with pymupdf.open(path) as pdf:
        for idx, page in enumerate(pdf):
            tables = extract_tables(page, idx + 1)
            bboxes = [t.bbox for t in tables]
            blocks = [b for b in extract_blocks(page) if not _in_table(b, bboxes)]
            ordered = order_blocks(blocks, page.rect.width)
            raw_texts.append("\n".join(b.text for b in ordered))
            tables_by_page.append(tables)

    cleaned, template = strip_running_headers(raw_texts)
    crumb = template[:-2].rstrip() if template and template.endswith(" #") else template
    pages = [
        LoadedPage(
            page=i + 1,
            section=crumb or f"Page {i + 1}",
            prose=normalize_text(text),
            tables=tables_by_page[i],
        )
        for i, text in enumerate(cleaned)
    ]
    return LoadedDoc(source_path=os.path.basename(str(path)), pages=pages)
