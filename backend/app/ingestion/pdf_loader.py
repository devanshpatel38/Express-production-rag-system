"""Two-pass PDF loader: per-page prose + validated tables (no figure handling in GPO v1)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf

from app.config import get_settings
from app.ingestion.pdf_layout import Block, order_blocks
from app.ingestion.pdf_tables import TableData, extract_tables
from app.ingestion.pdf_text import (
    collect_repeating_lines,
    normalize_text,
    section_for,
    strip_repeating,
)


@dataclass
class PageContent:
    page: int  # 1-based
    prose_text: str
    tables: list[TableData] = field(default_factory=list)
    section: str | None = None  # breadcrumb from the page's top line, if it is a section title


def _text_blocks(page) -> list[Block]:
    return [
        Block(b[0], b[1], b[2], b[3], b[4])
        for b in page.get_text("blocks")
        if b[6] == 0 and b[4].strip()
    ]


def _top_bottom(blocks: list[Block]) -> tuple[str, str]:
    """First line of the topmost block and last line of the bottommost block."""
    if not blocks:
        return "", ""
    ordered = sorted(blocks, key=lambda b: (b.y0, b.x0))
    top = ordered[0].text.strip().split("\n")[0]
    bottom = max(blocks, key=lambda b: (b.y1, b.x0)).text.strip().split("\n")[-1]
    return normalize_text(top), normalize_text(bottom)


def _inside(b: Block, bbox, tol: float = 2.0) -> bool:
    """True if the block's centre lies within the (tolerance-expanded) table bbox."""
    cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
    return bbox[0] - tol <= cx <= bbox[2] + tol and bbox[1] - tol <= cy <= bbox[3] + tol


def load_pdf(pdf_path: str, max_pages: int | None = None) -> list[PageContent]:
    s = get_settings()
    out: list[PageContent] = []
    with pymupdf.open(pdf_path) as doc:
        n = len(doc) if max_pages is None else min(max_pages, len(doc))

        # Pass 1: repeating header/footer templates.
        top_bottom = [_top_bottom(_text_blocks(doc[i])) for i in range(n)]
        repeating = collect_repeating_lines(top_bottom, s.header_footer_min_recurrence)

        # Pass 2: tables, bbox subtraction, ordered prose.
        for pno in range(n):
            page = doc[pno]
            blocks = _text_blocks(page)
            tables = extract_tables(page, blocks)
            prose_blocks = [
                b for b in blocks if not any(_inside(b, t.bbox) for t in tables if t.bbox)
            ]
            ordered = order_blocks(prose_blocks, page.rect.width)
            text = "\n".join(b.text.strip() for b in ordered)
            text = normalize_text(strip_repeating(normalize_text(text), repeating))
            if not text.strip() and not tables:
                continue
            section = section_for(top_bottom[pno][0])
            out.append(PageContent(page=pno + 1, prose_text=text, tables=tables, section=section))
    return out
