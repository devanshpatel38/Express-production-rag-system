import os

import pytest

from app.ingestion.pdf_loader import PageContent, load_pdf

PDF = os.path.join(os.path.dirname(__file__), "..", "..", "GPO-Anual-report.pdf")

pytestmark = pytest.mark.skipif(not os.path.exists(PDF), reason="GPO PDF not present")


@pytest.fixture(scope="module")
def pages():
    return load_pdf(PDF, max_pages=90)


def test_no_empty_pages(pages):
    assert pages
    for p in pages:
        assert isinstance(p, PageContent)
        assert p.prose_text.strip() or p.tables


def test_banner_not_letter_spaced(pages):
    joined = "\n".join(p.prose_text for p in pages)
    assert "G O V E R N M E N T" not in joined


def test_pages_are_one_based_and_limited(pages):
    assert min(p.page for p in pages) >= 1
    assert max(p.page for p in pages) <= 90


def test_financial_table_page(pages):
    p81 = [p for p in pages if p.page == 81]
    assert p81 and p81[0].tables
    assert p81[0].tables[0].columns


def test_table_text_not_reindexed_as_prose(pages):
    p = next(p for p in pages if p.page == 81)
    t = p.tables[0]
    label = t.rows[0][0]
    assert label and label not in p.prose_text
