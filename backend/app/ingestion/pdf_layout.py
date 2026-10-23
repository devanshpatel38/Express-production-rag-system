"""Column-aware reading-order resolution for PDF text blocks (pure, stdlib only)."""
from __future__ import annotations

from dataclasses import dataclass


GUTTER_FRAC = 0.03  # min horizontal gap between columns, fraction of page width
CROSS_TOL_FRAC = 0.02  # margin each side of mid a block needs to count as full-width


@dataclass
class Block:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


def order_blocks(blocks: list[Block], page_width: float) -> list[Block]:
    if not blocks:
        return []
    mid = page_width / 2
    tol = CROSS_TOL_FRAC * page_width
    full = [b for b in blocks if b.x0 < mid - tol and b.x1 > mid + tol]
    full_ids = {id(b) for b in full}
    col = [b for b in blocks if id(b) not in full_ids]
    left = [b for b in col if (b.x0 + b.x1) / 2 < mid]
    right = [b for b in col if (b.x0 + b.x1) / 2 >= mid]

    two_col = False
    if left and right:
        gap = min(b.x0 for b in right) - max(b.x1 for b in left)
        y_overlap = max(min(b.y0 for b in left), min(b.y0 for b in right)) < min(
            max(b.y1 for b in left), max(b.y1 for b in right)
        )
        two_col = gap >= GUTTER_FRAC * page_width and y_overlap
    if not two_col:
        return sorted(blocks, key=lambda b: b.y0)

    left_ids = {id(b) for b in left}
    separators = sorted(full, key=lambda b: b.y0)
    out: list[Block] = []
    prev = float("-inf")
    for sep in [*separators, None]:
        cur = sep.y0 if sep is not None else float("inf")
        band = [b for b in col if prev <= b.y0 < cur]
        out.extend(sorted((b for b in band if id(b) in left_ids), key=lambda b: b.y0))
        out.extend(sorted((b for b in band if id(b) not in left_ids), key=lambda b: b.y0))
        if sep is not None:
            out.append(sep)
        prev = cur
    return out
