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
