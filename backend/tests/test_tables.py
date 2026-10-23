import os

import pymupdf
import pytest

from app.ingestion.pdf_layout import Block
from app.ingestion.pdf_tables import extract_tables, is_valid_table, split_packed_row

PDF = os.path.join(os.path.dirname(__file__), "..", "..", "GPO-Anual-report.pdf")

pytestmark = pytest.mark.skipif(not os.path.exists(PDF), reason="GPO PDF not present")


def _blocks(page):
    return [
        Block(b[0], b[1], b[2], b[3], b[4])
        for b in page.get_text("blocks")
        if b[6] == 0
    ]


@pytest.fixture(scope="module")
def doc():
    d = pymupdf.open(PDF)
    yield d
    d.close()


def test_org_chart_rejected(doc):
    page = doc[27]
    assert extract_tables(page, _blocks(page)) == []


def test_financial_table_split(doc):
    page = doc[80]
    tables = extract_tables(page, _blocks(page))
    assert tables
    t = tables[0]
    assert t.units == "(Dollars in thousands)"
    assert t.columns == ["2018", "2017"]
    rows = [r for tb in tables for r in tb.rows]
    state = [r for r in rows if r[0] == "U.S. Department of State"]
    assert state
    label, vals = state[0]
    assert "270,596" in vals["2018"]
    assert "310,971" in vals["2017"]
    assert len(rows) == 6
    for label, vals in rows:
        assert label and label.strip()
        assert any(v and v.strip() for v in vals.values())


def test_mismatched_counts_fall_back():
    rows = split_packed_row("A\nB\nC", {"2018": "1\n2", "2017": "3\n4"})
    assert len(rows) == 1
    assert rows[0][0] == "A B C"
    assert rows[0][1] == {"2018": "1 2", "2017": "3 4"}


def test_matched_counts_zip():
    rows = split_packed_row("A\nB", {"2018": "1\n2", "2017": "3\n4"})
    assert rows == [("A", {"2018": "1", "2017": "3"}), ("B", {"2018": "2", "2017": "4"})]


def test_is_valid_table_rejects_inconsistent():
    assert is_valid_table([["a", "b"], ["c"]]) is False
