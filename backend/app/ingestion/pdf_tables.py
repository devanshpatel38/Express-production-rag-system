"""Table extraction for the GPO annual report.

PyMuPDF ``find_tables`` produces false positives (e.g. org charts) and packs several
logical rows of a financial table into single newline-separated cells. This module
validates grids and splits aligned stacks back into logical rows, never guessing an
alignment when line counts disagree.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ingestion.pdf_layout import Block

_YEAR = re.compile(r"^(19|20)\d{2}$")
_UNITS = re.compile(r"^\(.*(thousand|million|billion|dollar).*\)$", re.I | re.S)
_DIGIT = re.compile(r"\d")


@dataclass
class TableData:
    page: int  # 1-based
    title: str
    units: str
    columns: list[str]
    rows: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    bbox: tuple | None = None


def _clean(c) -> str:
    return "" if c is None else str(c).strip()


def is_valid_table(raw_rows: list[list], min_rows: int = 2) -> bool:
    """Reject grids that are not data tables (org charts, ragged or sparse grids).

    A valid grid has >= min_rows rows, >= 2 columns, a consistent column count,
    mostly filled cells, and numeric content (financial figures).
    """
    if not raw_rows or len(raw_rows) < min_rows:
        return False
    ncols = len(raw_rows[0])
    if ncols < 2 or any(len(r) != ncols for r in raw_rows):
        return False
    cells = [_clean(c) for r in raw_rows for c in r]
    filled = [c for c in cells if c]
    if not filled or len(filled) / len(cells) < 0.4:
        return False
    numeric = sum(1 for c in filled if _DIGIT.search(c))
    return numeric >= 2 and numeric / len(filled) >= 0.3


def _lines(cell: str) -> list[str]:
    return [ln.strip() for ln in cell.split("\n") if ln.strip()]


def split_packed_row(
    label_cell: str, value_cells: dict[str, str]
) -> list[tuple[str, dict[str, str]]]:
    """Split newline-packed label/value stacks into logical rows.

    Zips only when the label stack and every non-empty value stack have the same
    line count; otherwise returns one raw fallback row (newlines -> spaces).
    """
    labels = _lines(label_cell)
    stacks = {k: _lines(v) for k, v in value_cells.items() if _clean(v)}
    if not labels or not stacks:
        return []
    n = len(labels)
    if all(len(s) == n for s in stacks.values()):
        return [
            (labels[i], {k: s[i] for k, s in stacks.items()}) for i in range(n)
        ]
    return [
        (
            " ".join(labels),
            {k: " ".join(s) for k, s in stacks.items()},
        )
    ]


def _title_above(bbox, blocks: list[Block]) -> str:
    best = None
    for b in blocks:
        t = " ".join(b.text.split())
        if b.y1 <= bbox[1] + 1 and t and not _UNITS.match(t) and not _DIGIT.fullmatch(t):
            if best is None or b.y1 > best.y1:
                best = b
    return " ".join(best.text.split()) if best else ""


def _dedupe_columns(items: list[tuple[int, str]]) -> dict[int, str]:
    """Map column index -> unique name (later duplicates get '#2', '#3' ...)."""
    counts: dict[str, int] = {}
    out: dict[int, str] = {}
    for i, v in items:
        counts[v] = counts.get(v, 0) + 1
        out[i] = v if counts[v] == 1 else f"{v}#{counts[v]}"
    return out


def _table_rows(raw: list[list], page_no: int, title: str, bbox) -> TableData | None:
    units = ""
    columns: dict[int, str] = {}
    pending_labels = ""
    out: list[tuple[str, dict[str, str]]] = []
    for r in raw:
        cells = [_clean(c) for c in r]
        label, vals = cells[0], cells[1:]
        if not units:
            for c in cells:
                if c and _UNITS.match(c):
                    units = c
                    break
        if any(_UNITS.match(c) for c in cells if c):
            continue
        non_empty = [(i, v) for i, v in enumerate(vals, 1) if v]
        if non_empty and all(_YEAR.match(v) for _, v in non_empty):
            columns = _dedupe_columns(non_empty)
            if label:
                pending_labels = label  # labels share the header row (packed stack)
            continue
        if non_empty and not any(_DIGIT.search(v) for _, v in non_empty):
            continue  # sub-header such as "Billings % of Total"
        if not non_empty:
            if label:
                pending_labels = label
            continue
        row_label = label or pending_labels
        if label:
            pending_labels = ""
        elif row_label:
            pending_labels = ""
        last = max(columns) if columns else None
        named = {
            columns.get(i, f"col{i}"): v
            for i, v in non_empty
            if last is None or i <= last  # drop only cells trailing past the header
        }
        out.extend(split_packed_row(row_label, named))
    out = [(lb, v) for lb, v in out if lb.strip() and any(x.strip() for x in v.values())]
    if not out:
        return None
    ordered = [columns[i] for i in sorted(columns)] if columns else []
    seen = {k for _, v in out for k in v}
    used_columns = [c for c in ordered if c in seen] + sorted(seen - set(ordered))
    return TableData(
        page=page_no,
        title=title,
        units=units,
        columns=used_columns,
        rows=out,
        bbox=tuple(bbox),
    )


def extract_tables(page, page_text_blocks: list[Block]) -> list[TableData]:
    result: list[TableData] = []
    for t in page.find_tables().tables:
        raw = t.extract()
        if not is_valid_table(raw):
            continue
        td = _table_rows(raw, page.number + 1, _title_above(t.bbox, page_text_blocks), t.bbox)
        if td:
            result.append(td)
    return result
