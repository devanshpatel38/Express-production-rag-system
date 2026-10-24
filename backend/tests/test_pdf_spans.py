from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from app.config import get_settings
from app.ingestion.pdf_spans import Block, extract_blocks

_pdf = Path(get_settings().source_pdf_path)
if not _pdf.is_absolute():
    _pdf = Path(__file__).resolve().parents[1] / _pdf
pytestmark = pytest.mark.skipif(not _pdf.exists(), reason="source PDF absent")


@pytest.fixture(scope="module")
def pages():
    doc = pymupdf.open(_pdf)
    yield [" ".join(b.text for b in extract_blocks(p)) for p in doc], doc
    doc.close()


def test_blocks_shape(pages):
    blocks = extract_blocks(pages[1][0])
    assert blocks and all(isinstance(b, Block) for b in blocks)
    assert all(isinstance(v, float) for b in blocks for v in (b.x0, b.y0, b.x1, b.y1))


def test_superscripts_stripped(pages):
    texts = pages[0]
    assert "electricity9" not in texts[1] and "electricity" in texts[1]
    assert "chemistry5" not in texts[0] and "chemistry" in texts[0]


def test_body_numbers_kept(pages):
    assert "391 kg CO" in pages[0][9]
    assert "391" in pages[0][9]
