"""Multi-column reading-order resolution over page blocks (pure geometry).

The gutter is derived from the blocks' own x-extents, never a fixed page
center: "narrow" blocks (not spanning most of the page) have their x-intervals
merged, and a sufficiently wide empty gap between merged intervals with
narrow blocks on both sides is the gutter. A block whose x-range straddles
the gutter is full-width and splits the page into horizontal bands. Within a
band, left-column blocks (top->bottom) precede right-column blocks.
"""
from __future__ import annotations

from app.ingestion.pdf_spans import Block

# Blocks wider than this fraction of the page are never column members.
_NARROW_MAX_FRAC = 0.65
# Minimum gutter width as a fraction of page width.
_MIN_GUTTER_FRAC = 0.015


def _find_gutter(blocks: list[Block], page_width: float) -> tuple[float, float] | None:
    """Return (gutter_x0, gutter_x1) or None for a single-column page."""
    narrow = [b for b in blocks if (b.x1 - b.x0) <= _NARROW_MAX_FRAC * page_width]
    if len(narrow) < 2:
        return None
    spans = sorted((b.x0, b.x1) for b in narrow)
    merged: list[list[float]] = [list(spans[0])]
    for x0, x1 in spans[1:]:
        if x0 <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], x1)
        else:
            merged.append([x0, x1])
    best: tuple[float, float] | None = None
    for left, right in zip(merged, merged[1:]):
        gap = right[0] - left[1]
        if gap >= _MIN_GUTTER_FRAC * page_width and (
            best is None or gap > best[1] - best[0]
        ):
            best = (left[1], right[0])
    return best


def order_blocks(blocks: list[Block], page_width: float) -> list[Block]:
    """Return blocks in human reading order (bands, then left/right columns)."""
    if len(blocks) < 2:
        return list(blocks)
    by_y = sorted(blocks, key=lambda b: (b.y0, b.x0))
    gutter = _find_gutter(blocks, page_width)
    if gutter is None:
        return by_y

    g0, g1 = gutter
    mid = (g0 + g1) / 2

    def full_width(b: Block) -> bool:
        return b.x0 < g0 and b.x1 > g1

    out: list[Block] = []
    left: list[Block] = []
    right: list[Block] = []

    def flush() -> None:
        out.extend(left)
        out.extend(right)
        left.clear()
        right.clear()

    for b in by_y:
        if full_width(b):
            flush()
            out.append(b)
        elif (b.x0 + b.x1) / 2 < mid:
            left.append(b)
        else:
            right.append(b)
    flush()
    return out
