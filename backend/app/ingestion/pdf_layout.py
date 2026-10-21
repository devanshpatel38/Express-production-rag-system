"""Reading-order resolution for PDF text blocks.

Pure stdlib: no PyMuPDF, no I/O. Blocks are assumed to carry PDF-style
coordinates (y grows downward, so smaller y0 is higher on the page).
"""

from __future__ import annotations

from dataclasses import dataclass

# Minimum horizontal gap (in page units) between the left-column centroid
# group and the right-column group for the page to count as two-column.
# 15% of page width: real gutters are ~10-20% of a letter-size page, while
# intra-column variation in x-centers is far smaller.
COLUMN_GAP_FRACTION = 0.15


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


def _is_two_column(blocks: list[Block], page_width: float) -> bool:
    mid = page_width / 2.0
    left = [b.xc for b in blocks if b.xc < mid]
    right = [b.xc for b in blocks if b.xc >= mid]
    if not left or not right:
        return False
    gap = min(right) - max(left)
    return gap >= COLUMN_GAP_FRACTION * page_width


def order_blocks(blocks: list[Block], page_width: float) -> list[Block]:
    """Return blocks in human reading order.

    Two-column pages: left column top-to-bottom, then right column top-to-bottom.
    Single-column pages: all blocks top-to-bottom.
    """
    if _is_two_column(blocks, page_width):
        mid = page_width / 2.0
        left = sorted((b for b in blocks if b.xc < mid), key=lambda b: b.y0)
        right = sorted((b for b in blocks if b.xc >= mid), key=lambda b: b.y0)
        return left + right
    return sorted(blocks, key=lambda b: b.y0)
