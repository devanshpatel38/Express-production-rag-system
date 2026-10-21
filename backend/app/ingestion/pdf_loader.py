"""PDF loader orchestration: tables -> subtract -> prose -> strip -> normalize.

Two passes over the document:
  1. Collect running header/footer templates (top and bottom text block of every
     page) so they can be recognised by recurrence.
  2. Per page: extract tables, detect + describe figures, remove every text block
     lying inside a table or figure bbox (so cells / figure labels are not also
     indexed as prose), order the remaining blocks, strip headers/footers and
     normalize.

``PageContent.page`` is the 1-based PDF page number (the authoritative page
number for all downstream chunk metadata).
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

import pymupdf

from app.config import get_settings
from app.ingestion.pdf_figures import FigureContent, describe_figures, detect_figure_regions
from app.ingestion.pdf_layout import Block, order_blocks
from app.ingestion.pdf_tables import TableData, extract_tables
from app.ingestion.pdf_text import collect_repeating_lines, normalize_text, strip_repeating

_INSIDE_FRACTION = 0.5  # a block is "inside" a bbox if >= this share of its area is


@dataclass
class PageContent:
    page: int
    prose_text: str
    tables: list[TableData] = field(default_factory=list)
    figures: list[FigureContent] = field(default_factory=list)


def _text_blocks(page) -> list[Block]:
    return [
        Block(b[0], b[1], b[2], b[3], b[4])
        for b in page.get_text("blocks")
        if b[6] == 0 and b[4].strip()
    ]


def _inside(block: Block, bbox: tuple[float, float, float, float]) -> bool:
    w = min(block.x1, bbox[2]) - max(block.x0, bbox[0])
    h = min(block.y1, bbox[3]) - max(block.y0, bbox[1])
    if w <= 0 or h <= 0:
        return False
    area = max((block.x1 - block.x0) * (block.y1 - block.y0), 1e-6)
    return (w * h) / area >= _INSIDE_FRACTION


def subtract_regions(blocks: list[Block], bboxes) -> list[Block]:
    return [b for b in blocks if not any(_inside(b, bb) for bb in bboxes)]


def _edge_texts(blocks: list[Block]) -> tuple[str, str]:
    """Text of the topmost and bottommost block (newlines trimmed, spaces kept)."""
    if not blocks:
        return "", ""
    ordered = sorted(blocks, key=lambda b: (b.y0, b.x0))
    return ordered[0].text.strip("\n"), ordered[-1].text.strip("\n")


_HASH_RUN = re.compile(r"#+")


def _expand_digit_widths(templates: set[str]) -> set[str]:
    """Add shorter digit-run variants of each template.

    Page numbers have varying width (3, 29, 112), so the single-digit pages would
    each mask to a different template ("#" vs "##") and fall below the recurrence
    threshold. Shorter variants make those header lines match too.
    """
    out = set(templates)
    for t in templates:
        runs = list(_HASH_RUN.finditer(t))
        if not runs:
            continue
        for lens in itertools.product(*[range(1, len(m.group()) + 1) for m in runs]):
            parts, last = [], 0
            for m, n in zip(runs, lens):
                parts.append(t[last:m.start()])
                parts.append("#" * n)
                last = m.end()
            parts.append(t[last:])
            out.add("".join(parts))
    return out


def _tail(text: str) -> str:
    """Block text without its first line (drops a varying section label)."""
    lines = text.split(chr(10), 1)
    return lines[1] if len(lines) > 1 else ""


def _mask(s: str) -> str:
    return re.sub(r"[0-9]", "#", s)


def load_pdf(
    pdf_path: str, describe_figures_fn=None, max_pages: int | None = None
) -> list[PageContent]:
    """Load a PDF into per-page content. ``max_pages`` limits pages (testing aid)."""
    s = get_settings()
    describer = describe_figures_fn
    if describer is None and s.vision_enabled:
        from app.rag.vision import get_vision_describer

        describer = get_vision_describer()

    doc = pymupdf.open(pdf_path)
    try:
        n = len(doc) if max_pages is None else min(len(doc), max_pages)

        # Pass 1: repeating header/footer templates.
        edges = [_edge_texts(_text_blocks(doc[i])) for i in range(n)]
        repeating = _expand_digit_widths(
            collect_repeating_lines(edges, s.header_footer_min_recurrence)
        )

        # Headers carry a varying section label on their first line ("STATISTICAL
        # APPENDIX" / "SELECTED TOPICS"), each too rare to cross the threshold on
        # its own. Their remaining lines are constant, so also learn those tails.
        tails = _expand_digit_widths(
            collect_repeating_lines(
                [(_tail(t), _tail(b)) for t, b in edges], s.header_footer_min_recurrence
            )
        )
        tails = {t for t in tails if any(c.isalpha() for c in t)}

        # Pass 2: per-page content.
        out: list[PageContent] = []
        for pno in range(n):
            page = doc[pno]
            blocks = _text_blocks(page)

            tables = extract_tables(page, blocks)
            regions = detect_figure_regions(page, s.figure_caption_regex)
            figures: list[FigureContent] = []
            if regions and describer is not None:
                figures = describe_figures(page, regions, describer)

            bboxes = [t.bbox for t in tables] + [bb for _, bb in regions]
            prose_blocks = subtract_regions(blocks, bboxes)
            if prose_blocks:
                srt = sorted(prose_blocks, key=lambda b: (b.y0, b.x0))
                edge_ids = {id(srt[0]), id(srt[-1])}
                prose_blocks = [
                    b for b in prose_blocks
                    if not (id(b) in edge_ids and _mask(_tail(b.text.strip("\n"))) in tails)
                ]
            ordered = order_blocks(prose_blocks, page.rect.width)
            kept = [strip_repeating(b.text.strip("\n"), repeating) for b in ordered]
            prose = normalize_text("\n".join(k for k in kept if k.strip()))

            for t in tables:
                t.page = pno + 1
            for f in figures:
                f.page = pno + 1
            if not (prose or tables or figures):
                continue
            out.append(PageContent(page=pno + 1, prose_text=prose, tables=tables, figures=figures))
        return out
    finally:
        doc.close()
