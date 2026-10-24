"""Span-aware PDF text extraction that strips superscript footnote markers.

PyMuPDF's plain block text glues tiny footnote digits onto the preceding word
(``electricity9``). Here we read the span-level dict and drop numeric-only
spans that are much smaller than the line's body text.

Observed on the iMac PER: markers are ~0.66-0.67 of body size (5.0 vs 7.5,
7.3 vs 11.0, 4.7 vs 7.0), so THRESHOLD=0.8 separates them from body digits
(same size as surrounding text, ratio 1.0).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf

SUPERSCRIPT_SIZE_RATIO = 0.8  # span size <= body size * ratio => candidate marker
_NUMERIC_RE = re.compile(r"^[\d\s.,;:()\[\]*†‡]*\d[\d\s.,;:()\[\]*†‡]*$")
# Chemical subscripts (CO2e, CH4) are small digits too, but meaningful: keep them.
_CHEM_PREFIX_RE = re.compile(r"(?:CO|CH|N|O|H|SF|NF)$")


@dataclass(frozen=True)
class Block:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


def _is_numeric_only(text: str) -> bool:
    return bool(_NUMERIC_RE.match(text.strip()))


def _body_size(spans: list[dict]) -> float:
    """Size of the span with the most non-whitespace characters on the line."""
    best = max(spans, key=lambda s: len("".join(s.get("text", "").split())))
    return float(best["size"])


def _line_text(spans: list[dict]) -> str:
    body = _body_size(spans)
    out: list[str] = []
    for s in spans:
        text = s.get("text", "")
        if (
            _is_numeric_only(text)
            and float(s["size"]) <= body * SUPERSCRIPT_SIZE_RATIO
            and not _CHEM_PREFIX_RE.search("".join(out).rstrip())
        ):
            continue
        out.append(text)
    return "".join(out)


def extract_blocks(page: "pymupdf.Page") -> list[Block]:
    """Return text blocks in the page's natural order, markers removed.

    Spans are concatenated as-is (they carry their own spaces); lines are
    joined with "\n". Whitespace normalisation is left to the loader.
    """
    blocks: list[Block] = []
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type", 0) != 0:
            continue
        lines = [
            _line_text(l["spans"]).rstrip("\n")
            for l in b.get("lines", [])
            if l.get("spans")
        ]
        text = "\n".join(t for t in lines if t.strip())
        if not text.strip():
            continue
        x0, y0, x1, y1 = b["bbox"]
        blocks.append(Block(float(x0), float(y0), float(x1), float(y1), text))
    return blocks
