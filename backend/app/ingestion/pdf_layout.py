"""Column-aware reading-order resolution for PDF text blocks (pure, stdlib only)."""
from __future__ import annotations

from dataclasses import dataclass


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
    full = [b for b in blocks if b.x0 <= mid <= b.x1]
    col = [b for b in blocks if not (b.x0 <= mid <= b.x1)]
    left = [b for b in col if (b.x0 + b.x1) / 2 < mid]
    right = [b for b in col if (b.x0 + b.x1) / 2 >= mid]

    two_col = bool(left) and bool(right) and max(b.x1 for b in left) < min(b.x0 for b in right)
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
