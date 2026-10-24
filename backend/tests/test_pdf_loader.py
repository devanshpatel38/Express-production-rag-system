from pathlib import Path

import pytest

pytest.importorskip("pymupdf")

from app.config import get_settings
from app.ingestion.pdf_loader import load_pdf

_pdf = Path(get_settings().source_pdf_path)
if not _pdf.is_absolute():
    _pdf = Path(__file__).resolve().parents[1] / _pdf
pytestmark = pytest.mark.skipif(not _pdf.exists(), reason="source PDF absent")


@pytest.fixture(scope="module")
def doc():
    return load_pdf(str(_pdf))


def test_pages_and_numbering(doc):
    assert len(doc.pages) == 12
    assert doc.pages[0].page == 1
    assert doc.pages[-1].page == 12
    assert doc.source_path == "iMac_PER_Oct2024.pdf"


def test_header_removed_and_section(doc):
    for p in doc.pages:
        assert "iMac | Product Environmental Report" not in p.prose
        assert p.section == "iMac | Product Environmental Report"


def test_prose_content(doc):
    text = "\n".join(p.prose for p in doc.pages)
    assert "electricity" in text
    assert "electricity9" not in text
    assert "346 kg CO2e" in text


def test_power_table_page(doc):
    assert len(doc.pages[11].tables) >= 1
