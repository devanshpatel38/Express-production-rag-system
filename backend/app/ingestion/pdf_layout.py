"""Reading-order resolution for PDF text blocks.

Pure stdlib: no PyMuPDF, no I/O. Blocks are assumed to carry PDF-style
coordinates (y grows downward, so smaller y0 is higher on the page).
"""

from __future__ import annotations

from dataclasses import dataclass

# Minimum width of the vertical gutter between the left and right column
# extents, as a fraction of page width. ~2% (about 12pt on a 612pt page)
# rejects accidental near-touching extents while accepting real gutters.
GUTTER_MIN_FRACTION = 0.02


@dataclass
class Block:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2.0


def _split_two_column(blocks: list[Block], mid: float, page_width: float):
    """Return (left, right, full) if the page is two-column, else None.

    `full` are blocks crossing the midline (titles, full-width body, footers).
    `left`/`right` are the remaining blocks split by x-center. The page is
    two-column only if both sides are non-empty and their horizontal extents
    are separated by a real vertical gutter.
    """
    full = [b for b in blocks if b.x0 <= mid <= b.x1]
    col = [b for b in blocks if not (b.x0 <= mid <= b.x1)]
    left = [b for b in col if b.xc < mid]
    right = [b for b in col if b.xc >= mid]
    if not left or not right:
        return None
    gutter = min(b.x0 for b in right) - max(b.x1 for b in left)
    if gutter < GUTTER_MIN_FRACTION * page_width:
        return None
    return left, right, full


def order_blocks(blocks: list[Block], page_width: float) -> list[Block]:
    """Return blocks in human reading order.

    Single-column pages (the default): all blocks sorted top-to-bottom.

    Two-column pages: the column region is split into horizontal bands by the
    full-width blocks (titles, footers). Within each band the left column is
    emitted top-to-bottom, then the right column; full-width blocks are emitted
    in their own y position between bands.
    """
    mid = page_width / 2.0
    split = _split_two_column(blocks, mid, page_width)
    if split is None:
        return sorted(blocks, key=lambda b: b.y0)

    left, right, full = split
    full_sorted = sorted(full, key=lambda b: b.y0)

    out: list[Block] = []
    band_lo = float("-inf")
    for sep in full_sorted:
        band_hi = sep.y0
        out.extend(_emit_band(left, right, band_lo, band_hi))
        out.append(sep)
        band_lo = band_hi
    out.extend(_emit_band(left, right, band_lo, float("inf")))
    return out


def _emit_band(left, right, lo: float, hi: float) -> list[Block]:
    """Left column then right column for blocks whose y0 is in [lo, hi)."""
    l_band = sorted((b for b in left if lo <= b.y0 < hi), key=lambda b: b.y0)
    r_band = sorted((b for b in right if lo <= b.y0 < hi), key=lambda b: b.y0)
    return l_band + r_band
