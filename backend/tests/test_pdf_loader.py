import pytest

from app.ingestion.pdf_loader import PageContent, load_pdf

PDF = "../GEP-Jun-2026.pdf"


class _Noop:
    def describe(self, image_png: bytes, caption: str) -> str:
        return ""


noop_describer = _Noop()


@pytest.fixture(scope="module")
def pages():
    return load_pdf(PDF, describe_figures_fn=noop_describer)


def test_blank_page_skipped(pages):
    assert pages
    assert all(isinstance(p, PageContent) for p in pages)
    assert all(p.prose_text or p.tables or p.figures for p in pages)


def test_running_header_absent_from_prose(pages):
    joined = " ".join(p.prose_text for p in pages)
    assert "GLOBAL ECONOMIC PROSPECTS | JUNE" not in joined


def test_table_page_yields_tabledata(pages):
    # 0-based index 100 -> 1-based page 101 (controller ruling R10)
    by_page = {p.page: p for p in pages}
    assert by_page[101].tables and by_page[101].tables[0].columns
    assert all(t.page == 101 for t in by_page[101].tables)


def test_pages_are_one_based_and_sorted(pages):
    nums = [p.page for p in pages]
    assert nums == sorted(nums) and min(nums) >= 1


def test_table_text_not_duplicated_in_prose(pages):
    p = {p.page: p for p in pages}[101]
    t = p.tables[0]
    label = next(l for l, _ in t.rows if len(l) > 8)
    assert label not in p.prose_text
