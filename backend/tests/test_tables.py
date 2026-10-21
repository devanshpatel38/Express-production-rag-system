import pymupdf
import pytest

from app.ingestion.pdf_layout import Block
from app.ingestion.pdf_tables import extract_tables, is_valid_table

PDF = "../GEP-Jun-2026.pdf"


@pytest.fixture(scope="module")
def page_and_blocks():
    doc = pymupdf.open(PDF)
    page = doc[100]
    blocks = [
        Block(b[0], b[1], b[2], b[3], b[4])
        for b in page.get_text("blocks")
        if b[6] == 0
    ]
    return page, blocks


def test_page100_table_has_year_columns(page_and_blocks):
    tds = extract_tables(*page_and_blocks)
    assert tds
    cols = tds[0].columns
    assert "2026f" in cols and "2027f" in cols


def test_page100_rows_have_labels_not_none(page_and_blocks):
    tds = extract_tables(*page_and_blocks)
    n = 0
    for td in tds:
        for label, cells in td.rows:
            n += 1
            assert label and label.strip()
            assert "None" not in label
            assert any(v and v.strip() for v in cells.values())
    assert n >= 10


def test_page100_exact_figures(page_and_blocks):
    td = extract_tables(*page_and_blocks)[0]
    rows = dict(td.rows)
    assert "TABLE 2.11" in td.title
    assert "percent" in td.units
    gdp = next(c for l, c in td.rows if l.startswith("EMDE SSA, GDP"))
    assert gdp["2023"] == "3.0" and gdp["2025e"] == "4.1" and gdp["2027f"] == "4.4"
    assert gdp["2028f"] == "4.5"
    assert "Private consumption" in rows
    assert rows["Public consumption"]["2026f"] == "-1.0"


def test_rejects_inconsistent_grid():
    assert is_valid_table([["a", "b"], ["c"]]) is False


def test_rejects_sparse_or_short_grid():
    assert is_valid_table([["", ""], ["", ""]]) is False
    assert is_valid_table([["1", "2"]]) is False
    assert is_valid_table([["1", "2"], ["3", "4"]]) is True


def test_page100_drops_spanning_caption_rows(page_and_blocks):
    td = extract_tables(*page_and_blocks)[0]
    assert all(not l.startswith("(Average") for l, _ in td.rows)
    assert len(td.rows) == 14


def test_page100_no_fabricated_labels(page_and_blocks):
    import re
    for td in extract_tables(*page_and_blocks):
        for label, _ in td.rows:
            assert not re.search(r"\brow \d+$", label)


# ---- synthetic row-assignment tests -------------------------------------
from app.ingestion.pdf_tables import _assign_rows

CENTERS = [100.0, 140.0]
NAMES = ["2024", "2025f"]


def W(x, y, text):
    return (x, y, x + 10, y + 8, text)


def run(rows):
    return _assign_rows(rows, CENTERS, NAMES, 20.0, 80.0)


def test_wrapped_label_first_line_is_kept():
    rows = [
        [W(10, 0, "Net exports, contribution")],
        [W(10, 10, "to growth"), W(95, 10, "1.1"), W(135, 10, "2.2")],
    ]
    out, dropped = run(rows)
    assert out == [("Net exports, contribution to growth", {"2024": "1.1", "2025f": "2.2"})]
    assert dropped == 0


def test_empty_label_carries_forward_not_fabricated():
    rows = [
        [W(10, 0, "Memo items")],
        [W(95, 10, "1.1"), W(135, 10, "2.2")],
    ]
    out, _ = run(rows)
    assert out[0][0] == "Memo items"


def test_no_label_anywhere_drops_row():
    out, dropped = run([[W(95, 0, "1.1"), W(135, 0, "2.2")]])
    assert out == [] and dropped == 1


def test_value_collision_drops_row():
    rows = [
        [W(10, 0, "Good"), W(95, 0, "1.0")],
        [W(10, 10, "Bad"), W(95, 10, "1.1"), W(98, 10, "9.9")],
    ]
    out, dropped = run(rows)
    assert [l for l, _ in out] == ["Good"] and dropped == 1


def test_stray_marker_keeps_numeric_row():
    rows = [[W(10, 0, "Exports"), W(95, 0, "1.1"), W(135, 0, "2.2"), W(150, 0, "a/")]]
    out, _ = run(rows)
    assert out == [("Exports", {"2024": "1.1", "2025f": "2.2"})]


def test_prose_row_without_numbers_is_not_data():
    out, _ = run([[W(10, 0, "(Average"), W(150, 0, "including")]])
    assert out == []
