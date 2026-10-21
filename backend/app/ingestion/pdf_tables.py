"""Table extraction for PDF pages with row-label re-association.

PyMuPDF's ``find_tables()`` is used to *locate* numeric grids, but on the
World Bank forecast tables it (a) fragments one logical table into several
pieces, (b) drops the left-hand label column, and (c) can miss columns. So the
detected fragments are validated and merged into one region, and rows are then
rebuilt from positioned words: the label is the text left of the first value
column on the same baseline, values are assigned to the nearest header column.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingestion.pdf_layout import Block

YEAR_RE = re.compile(r"^(?:19|20)\d{2}[a-z]?$")
NUM_RE = re.compile(r"^[-\u2212\u2013+]?\d[\d,]*(?:\.\d+)?%?$")
UNITS_RE = re.compile(
    r"\bpercent\b|U\.S\. dollars|\bbillion\b|\bmillion\b|\bindex\b|share of", re.I
)
Y_TOL = 3.0  # words within this many points vertically share a row
MERGE_GAP = 25.0  # max gap between fragments of one logical table
MIN_FILLED = 0.5


@dataclass
class TableData:
    page: int
    title: str
    units: str
    columns: list[str]
    rows: list[tuple[str, dict[str, str]]]
    bbox: tuple[float, float, float, float]


def _blank(v) -> bool:
    return v is None or not str(v).strip()


def is_valid_table(raw_rows: list[list], min_rows: int = 2) -> bool:
    """Reject false-positive grids: too short, ragged, one-column or mostly empty."""
    if not raw_rows or len(raw_rows) < min_rows:
        return False
    width = len(raw_rows[0])
    if width < 2 or any(len(r) != width for r in raw_rows):
        return False
    cells = [c for r in raw_rows for c in r]
    filled = sum(1 for c in cells if not _blank(c))
    return filled / len(cells) >= MIN_FILLED


def _overlap(a0, a1, b0, b1) -> float:
    return min(a1, b1) - max(a0, b0)


def _cluster(boxes: list[tuple]) -> list[list[int]]:
    """Group fragment bboxes that touch horizontally (shared y-band) or stack
    vertically (shared x-range)."""
    parent = list(range(len(boxes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            xo = _overlap(a[0], a[2], b[0], b[2])
            yo = _overlap(a[1], a[3], b[1], b[3])
            xgap, ygap = -xo, -yo
            if (yo > 0 and xgap <= MERGE_GAP) or (xo > 0 and ygap <= MERGE_GAP):
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(boxes)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _y_rows(words: list[tuple]) -> list[list[tuple]]:
    """Cluster words into visual rows by vertical centre."""
    rows: list[tuple[float, list[tuple]]] = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        yc = (w[1] + w[3]) / 2
        if rows and abs(yc - rows[-1][0]) <= Y_TOL:
            rows[-1][1].append(w)
        else:
            rows.append((yc, [w]))
    return [sorted(ws, key=lambda w: w[0]) for _, ws in rows]


def _is_value(tok: str) -> bool:
    return bool(NUM_RE.match(tok)) or tok in {"..", "...", "\u2013", "-"}


def _clean(text: str) -> str:
    return " ".join(text.split())


def _title_units(blocks: list[Block], region, header_y: float) -> tuple[str, str]:
    x0, y0, x1, y1 = region
    above = [
        b for b in blocks
        if b.y1 <= header_y + 1 and _overlap(b.x0, b.x1, x0 - 300, x1) > 0
    ]
    above.sort(key=lambda b: -b.y1)  # nearest first
    title = ""
    for b in above:
        first = _clean(b.text.strip().splitlines()[0]) if b.text.strip() else ""
        if re.match(r"^(TABLE|Table|FIGURE|Figure)\b", first):
            title = _clean(b.text)
            break
    units = ""
    for b in above:
        t = _clean(b.text)
        if t == title or not t:
            continue
        if UNITS_RE.search(t) and (t.startswith("(") or "," in t or len(t) > 25):
            units = t.strip("() ")
            break
    return title, units


def _caption_above(blocks: list[Block], xa: float, xb: float, header_y: float) -> str:
    near = [
        b for b in blocks
        if b.y1 <= header_y + 1 and header_y - b.y0 <= 45
        and _overlap(b.x0, b.x1, xa, xb) > 0 and (b.x1 - b.x0) < 200
        and not re.match(r"^\s*(TABLE|Table)", b.text)
    ]
    near.sort(key=lambda b: (b.y0, b.x0))
    return _clean(" ".join(b.text for b in near))


def _find_header(rows: list[list[tuple]]):
    """Index and year-words of the first row holding >=2 year tokens."""
    for i, r in enumerate(rows):
        hw = [w for w in r if YEAR_RE.match(w[4])]
        if len(hw) >= 2:
            return i, hw
    return None, []


def _name_columns(hw: list[tuple], blocks: list[Block], header_y: float) -> list[str]:
    """Header names; a repeated year starts a second group, suffixed by its caption."""
    names = [w[4] for w in hw]
    seen: set[str] = set()
    dup_idx = []
    for i, n in enumerate(names):
        if n in seen:
            dup_idx.append(i)
        seen.add(n)
    if dup_idx:
        cap = _caption_above(blocks, hw[dup_idx[0]][0] - 5, hw[dup_idx[-1]][2] + 5, header_y)
        for i in range(dup_idx[0], len(names)):
            names[i] = f"{names[i]} ({cap})" if cap else f"{names[i]} (2)"
    return names


def _assign_row(r: list[tuple], centers, names, tol, first_left):
    """Split one visual row into (label_text, cells, collision).

    Non-numeric tokens in the value area are ignored (stray markers); the
    caller decides what a row with no numeric cells means.
    """
    label_ws, cells, collision, nstray = [], {}, False, 0
    for w in r:
        xc = (w[0] + w[2]) / 2
        tok = w[4].strip()
        if xc < first_left:
            label_ws.append(w)
        elif _is_value(tok):
            k = min(range(len(centers)), key=lambda i: abs(centers[i] - xc))
            if abs(centers[k] - xc) <= tol:
                if names[k] in cells and cells[names[k]] != tok:
                    collision = True
                cells[names[k]] = tok
        else:
            nstray += 1
    # prose-dominated row (caption with a footnote digit): its few 'values' are not data
    stray = nstray > len(cells)
    if stray:
        cells = {}
    return _clean(" ".join(w[4] for w in label_ws)), cells, collision, stray


def _assign_rows(rows, centers, names, tol, first_left):
    """Turn visual rows into (label, cells) with label carry-forward.

    Returns (out, dropped). A row is dropped (never given an invented label)
    when it has values but no resolvable label, or when two different values
    land in one column.
    """
    out: list[tuple[str, dict[str, str]]] = []
    dropped = 0
    carry = ""  # nearest preceding value-less left-text line
    for r in rows:
        label, cells, collision, stray = _assign_row(r, centers, names, tol, first_left)
        if not cells:
            # heading / wrapped-label first line; prose captions (stray) never carry
            carry = label if (label and not stray) else ("" if stray else carry)
            continue
        if collision:
            dropped += 1
            continue
        if not label:
            label = carry
        elif carry and label[:1].islower():
            label = f"{carry} {label}"  # wrapped label: continuation line
        if not label:
            dropped += 1
            continue
        if _clean(" ".join(w[4] for w in r if (w[0] + w[2]) / 2 < first_left)):
            carry = ""  # a labelled value row ends any pending heading
        out.append((label, cells))
    return out, dropped


def _rows_from_words(page, region, blocks, title, units):
    """Header-driven row rebuild. Returns (names, rows) or None."""
    x0, y0, x1, y1 = region
    words = [
        w for w in page.get_text("words")
        if w[1] >= y0 - 2 and w[3] <= y1 + 2 and w[0] >= x0 - 300 and w[2] <= x1 + 5
        and w[4].strip()
    ]
    rows = _y_rows(words)
    header, hw = _find_header(rows)
    if header is None:
        return None
    centers = [(w[0] + w[2]) / 2 for w in hw]
    names = _name_columns(hw, blocks, rows[header][0][1])
    spacing = min((b - a for a, b in zip(centers, centers[1:])), default=40.0)
    tol = max(spacing * 0.5, 10.0)
    out, _dropped = _assign_rows(rows[header + 1:], centers, names, tol, centers[0] - tol)
    if len(out) < 2:
        return None
    return names, out


def _rows_from_grid(page, table, blocks, title):
    """Fallback for grids without a year header: left-label association by y-band."""
    raw = table.extract()
    if not raw:
        return None
    header = [_clean(str(c)) if not _blank(c) else f"col{i + 1}" for i, c in enumerate(raw[0])]
    words = page.get_text("words")
    bx0 = table.bbox[0]
    row_boxes = [getattr(r, "bbox", None) for r in table.rows]
    out = []
    carry = ""
    n = len(raw)
    for i, row in enumerate(raw[1:], start=1):
        if i < len(row_boxes) and row_boxes[i]:
            ry0, ry1 = row_boxes[i][1], row_boxes[i][3]
        else:
            h = (table.bbox[3] - table.bbox[1]) / n
            ry0, ry1 = table.bbox[1] + i * h, table.bbox[1] + (i + 1) * h
        lab = [
            w for w in words
            if w[2] <= bx0 + 1 and w[0] >= bx0 - 300 and _overlap(w[1], w[3], ry0, ry1) > 0.4 * (w[3] - w[1])
        ]
        label = _clean(" ".join(w[4] for w in sorted(lab, key=lambda w: w[0])))
        cells = {header[c]: str(v).strip() for c, v in enumerate(row) if not _blank(v)}
        if not cells:
            carry = label or carry
            continue
        label = label or carry
        if not label:
            continue  # never fabricate a label
        out.append((label, cells))
    return (header, out) if len(out) >= 2 else None


def extract_tables(page, page_text_blocks: list[Block]) -> list[TableData]:
    """Extract validated, label-complete tables from one PDF page."""
    try:
        found = page.find_tables().tables
    except Exception:
        return []
    frags = []
    for t in found:
        try:
            raw = t.extract()
        except Exception:
            continue
        if is_valid_table(raw):
            frags.append(t)
    if not frags:
        return []
    boxes = [tuple(t.bbox) for t in frags]
    results: list[TableData] = []
    for grp in _cluster(boxes):
        gb = [boxes[i] for i in grp]
        region = (min(b[0] for b in gb), min(b[1] for b in gb),
                  max(b[2] for b in gb), max(b[3] for b in gb))
        title, units = _title_units(page_text_blocks, region, region[1] + 12)
        built = _rows_from_words(page, region, page_text_blocks, title, units)
        if built is None and len(grp) == 1:
            built = _rows_from_grid(page, frags[grp[0]], page_text_blocks, title)
        if built is None:
            continue
        cols, rows = built
        results.append(TableData(page=page.number, title=title, units=units,
                                 columns=list(cols), rows=rows, bbox=region))
    results.sort(key=lambda t: (t.bbox[1], t.bbox[0]))
    return results
