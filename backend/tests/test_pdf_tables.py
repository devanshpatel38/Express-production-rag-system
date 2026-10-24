from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from app.config import get_settings
from app.ingestion.pdf_tables import TableRecord, extract_tables

_pdf = Path(get_settings().source_pdf_path)
if not _pdf.is_absolute():
    _pdf = Path(__file__).resolve().parents[1] / _pdf
pytestmark = pytest.mark.skipif(not _pdf.exists(), reason="source PDF absent")

POWER_PAGE_IDX = 11  # 0-based; 1-based page 12


@pytest.fixture(scope="module")
def doc():
    d = pymupdf.open(_pdf)
    yield d
    d.close()


def test_power_table_extracted(doc):
    tables = extract_tables(doc[POWER_PAGE_IDX], POWER_PAGE_IDX + 1)
    assert len(tables) == 1
    t = tables[0]
    assert isinstance(t, TableRecord)
    assert t.page == POWER_PAGE_IDX + 1  # 1-based
    assert list(t.rows[0].values) == ["100V", "115V", "230V"]
    assert t.units == "W"
    assert 0 < len(t.title) <= 80 and "Power consumption" in t.title
    by_label = {r.label: r.values for r in t.rows}
    assert by_label["Off"] == {"100V": "0.27W", "115V": "0.27W", "230V": "0.29W"}
    assert by_label["Sleep"]["115V"] == "0.57W"
    assert "Power adapter efficiency" in by_label
    x0, y0, x1, y1 = t.bbox
    assert y1 - y0 > 100 and x1 > x0


def test_infographic_page_yields_no_table(doc):
    assert extract_tables(doc[1], 2) == []


def test_fragment_pages_yield_no_table(doc):
    # page idx 9 holds label->value fragments (1x2 candidates)
    assert extract_tables(doc[9], 10) == []


def test_only_power_table_in_whole_document(doc):
    found = [(i + 1, len(extract_tables(p, i + 1))) for i, p in enumerate(doc)]
    assert [pg for pg, n in found if n] == [12]
