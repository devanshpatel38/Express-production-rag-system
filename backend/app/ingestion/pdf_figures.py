"""Figure detection and region rendering for GEP PDFs.

GEP charts are mostly vector drawings, not embedded images, so we render the
page region around each figure to PNG and hand it to a vision model.

Layout assumption (verified on the GEP): the "FIGURE n.n Title" caption sits at
the TOP of the figure, panels below, and a "Source(s):/Note(s):" block closes
it. The crop therefore runs from the caption down to the end of the first
Source/Note block in the same column (or the next caption / page bottom). The
crop is deliberately generous; the vision model reads whatever labels show.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf

from app.config import get_settings

COLUMN_WIDTH = 285.0  # points; GEP columns are ~270pt wide
PAGE_BOTTOM_MARGIN = 40.0
_END_RE = re.compile(r"^\s*(sources?|notes?)\s*:", re.I)


@dataclass
class FigureContent:
    page: int
    caption: str
    description: str


def detect_figure_regions(
    page, caption_regex: str | None = None
) -> list[tuple[str, tuple[float, float, float, float]]]:
    rx = re.compile(caption_regex or get_settings().figure_caption_regex)
    rect = page.rect
    blocks = [b for b in page.get_text("blocks") if b[6] == 0]

    caps = []
    for b in blocks:
        m = rx.search(b[4])
        if m:
            caption = re.sub(r"\s+", " ", b[4][m.start():]).strip()
            caps.append((caption, b))
    caps.sort(key=lambda c: (c[1][1], c[1][0]))

    regions = []
    for caption, cb in caps:
        cx0, cy0 = cb[0], cb[1]
        left = max(0.0, cx0 - 6)
        right = min(rect.width, left + COLUMN_WIDTH)
        bottom = rect.height - PAGE_BOTTOM_MARGIN

        # Next caption below in the same column limits the crop.
        for _, ob in caps:
            if ob is not cb and ob[1] > cy0 + 5 and ob[0] < right and ob[2] > left:
                bottom = min(bottom, ob[1] - 2)
        # First Source/Note block below the caption in the column closes the figure.
        ends = [
            b[3] for b in blocks
            if b[1] > cy0 and _END_RE.match(b[4]) and b[0] < right and b[2] > left
        ]
        if ends:
            bottom = min(bottom, min(ends) + 2)

        top = max(0.0, cy0 - 4)
        if bottom - top < 20:
            bottom = min(rect.height, top + 200)
        regions.append((caption, (left, top, right, bottom)))
    return regions


def describe_figures(page, regions, describer) -> list[FigureContent]:
    out = []
    for caption, bbox in regions:
        pix = page.get_pixmap(clip=pymupdf.Rect(bbox), matrix=pymupdf.Matrix(2, 2))
        desc = describer.describe(pix.tobytes("png"), caption)
        out.append(FigureContent(page=page.number, caption=caption, description=desc))
    return out
