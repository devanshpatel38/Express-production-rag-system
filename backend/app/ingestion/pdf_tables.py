"""Strict table extraction for the iMac PER PDF.

PyMuPDF ``find_tables()`` is mostly noise on this document: it shatters the
label->value facts into 1xN fragments, reads the carbon-footprint infographic
as a grid of ``None`` cells, and even splits the one genuine table (the
power-consumption table, 1-based page 12) into a 2-row header candidate plus
loose 1-row fragments. So ``find_tables`` is used only as an *anchor*:

1. every candidate is validated strictly (``_validate``);
2. a survivor supplies the header (column labels, descriptor sub-header, bbox);
3. body rows are rebuilt from the page's word positions below the header,
   aligned to the header's column x-centres, so rows lost by find_tables are
   recovered. Row labels come from the words left of the first column; a row
   with no label text or no value in every column is skipped (never invented).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import pymupdf

from app.ingestion.pdf_text import normalize_text

# Validation thresholds
MIN_DATA_COLUMNS = 2      # columns beyond the row-label column
MIN_ROWS = 2              # a single row is a fragment, not a table
MIN_FILLED_FRACTION = 0.6  # share of non-empty cells (infographic is ~0.25)
MAX_TITLE_CHARS = 80      # longer "captions" are prose, never a title
_ROW_Y_TOL = 3.0          # words within this y-centre distance share a row
_MAX_ROW_GAP = 14.0       # vertical gap that ends the table body

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
_UNIT_RE = re.compile(r"^\s*[-+]?\d[\d.,]*\s*(kWh|kW|W|%|V|kg|g)\b", re.I)
_UNIT_WORDS = {"watts": "W", "watt": "W", "kwh": "kWh"}


@dataclass
class TableRow:
    label: str
    values: dict[str, str]  # column header -> cell text (verbatim, with unit)


@dataclass
class TableRecord:
    title: str
    units: str
    page: int  # 1-based
    rows: list[TableRow] = field(default_factory=list)
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


def _clean(cell) -> str:
    return normalize_text(cell).replace("\n", " ").strip() if cell else ""


def _validate(grid: list[list]) -> bool:
    """Strict candidate check; see module thresholds."""
    if len(grid) < MIN_ROWS:
        return False
    ncols = {len(r) for r in grid}
    if len(ncols) != 1 or next(iter(ncols)) - 1 < MIN_DATA_COLUMNS:
        return False
    cells = [c for r in grid for c in r]
    filled = sum(1 for c in cells if c and str(c).strip())
    if filled / len(cells) < MIN_FILLED_FRACTION:
        return False
    return any(_NUM_RE.search(str(c)) for c in cells if c)


def _detect_units(texts: list[str]) -> str:
    counts: Counter[str] = Counter()
    for t in texts:
        m = _UNIT_RE.match(t)
        if m and m.group(1).upper() != "V":
            counts[m.group(1) if m.group(1) != "%" else "%"] += 1
        for w in re.findall(r"[A-Za-z]+", t):
            if w.lower() in _UNIT_WORDS:
                counts[_UNIT_WORDS[w.lower()]] += 1
    return counts.most_common(1)[0][0] if counts else ""


def _header_info(grid: list[list]) -> tuple[list[str], str] | None:
    """Return (column headers, descriptor title) from a validated header grid."""
    labelled = [r for r in grid if sum(1 for c in r[1:] if c and str(c).strip()) == len(r) - 1]
    if not labelled:
        return None
    cols = [_clean(c) for c in labelled[-1][1:]]
    title = ""
    for r in grid:
        if r is labelled[-1]:
            continue
        for c in r:
            t = _clean(c)
            if t and t.lower() != "mode" and len(t) <= MAX_TITLE_CHARS and not _NUM_RE.fullmatch(t):
                title = t
    return cols, title


def _rebuild_rows(page, bbox, cols: list[str]) -> tuple[list[TableRow], float]:
    """Read body rows below the header from word positions, aligned to columns."""
    words = page.get_text("words")
    header = [w for w in words if w[4] in cols and bbox[0] - 2 <= w[0] <= bbox[2] + 2
              and bbox[1] - 2 <= w[1] <= bbox[3] + 2]
    if len(header) < len(cols):
        return [], bbox[3]
    header.sort(key=lambda w: w[0])
    centres = [(w[0] + w[2]) / 2 for w in header[: len(cols)]]
    half = (centres[1] - centres[0]) / 2 if len(centres) > 1 else 30
    first_col_x0 = header[0][0]
    below = [w for w in words if w[1] >= bbox[3] - 1 and bbox[0] - 40 <= w[0] <= bbox[2] + 2]
    below.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[list] = []
    for w in below:
        yc = (w[1] + w[3]) / 2
        if lines and abs(lines[-1][0] - yc) <= _ROW_Y_TOL:
            lines[-1][1].append(w)
        else:
            lines.append([yc, [w]])
    rows: list[TableRow] = []
    last_y = bbox[3]
    bottom = bbox[3]
    for yc, ws in lines:
        if yc - last_y > _MAX_ROW_GAP + 6:
            break
        label_words = [w for w in ws if w[2] <= first_col_x0 - 4 or (w[0] + w[2]) / 2 < centres[0] - half]
        vals: dict[str, str] = {}
        for c, x in zip(cols, centres):
            hit = [w for w in ws if w not in label_words and abs((w[0] + w[2]) / 2 - x) <= half]
            if hit:
                vals[c] = " ".join(w[4] for w in sorted(hit, key=lambda w: w[0]))
        label = _clean(" ".join(w[4] for w in sorted(label_words, key=lambda w: w[0])))
        if not label or len(vals) != len(cols) or not any(_NUM_RE.search(v) for v in vals.values()):
            break  # end of table body (footnotes, prose, ...)
        rows.append(TableRow(label=label, values=vals))
        last_y = yc
        bottom = max(w[3] for w in ws)
    return rows, bottom


def extract_tables(page: "pymupdf.Page", page_number: int) -> list[TableRecord]:
    """Return strictly validated tables on ``page`` (``page_number`` is 1-based).

    ``bbox`` of each record spans the header plus all rebuilt body rows.
    """
    records: list[TableRecord] = []
    for cand in page.find_tables().tables:
        grid = cand.extract()
        if not _validate(grid):
            continue
        info = _header_info(grid)
        if info is None:
            continue
        cols, title = info
        x0, y0, x1, y1 = cand.bbox
        rows, bottom = _rebuild_rows(page, (x0, y0, x1, y1), cols)
        if not rows:
            continue
        units = _detect_units([v for r in rows for v in r.values.values()] + [title])
        records.append(TableRecord(title=title, units=units, page=page_number, rows=rows,
                                   bbox=(x0, y0, x1, max(y1, bottom))))
    return records
