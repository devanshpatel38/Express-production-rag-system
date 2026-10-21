import os
import re

import pymupdf
import pytest

from app.ingestion.pdf_figures import FigureContent, describe_figures, detect_figure_regions

PDF = "../GEP-Jun-2026.pdf"

pytestmark = pytest.mark.skipif(not os.path.exists(PDF), reason="GEP PDF not present")
CAPTION_REGEX = r"(?im)^\s*figure\s+\d+\.\d+"


@pytest.fixture(scope="module")
def sample_fig_page():
    doc = pymupdf.open(PDF)
    rx = re.compile(CAPTION_REGEX)
    for page in doc:
        if rx.search(page.get_text()):
            return page
    pytest.skip("no figure page found")


class FakeDescriber:
    def __init__(self, ret):
        self.ret = ret
        self.calls = []

    def describe(self, png_bytes, caption):
        self.calls.append((png_bytes, caption))
        return self.ret


def test_detects_figure_captions_on_sample_page(sample_fig_page):
    regions = detect_figure_regions(sample_fig_page, CAPTION_REGEX)
    assert len(regions) >= 1 and regions[0][0].lower().startswith("figure")
    x0, y0, x1, y1 = regions[0][1]
    r = sample_fig_page.rect
    assert 0 <= x0 < x1 <= r.width and 0 <= y0 < y1 <= r.height
    assert (y1 - y0) > 100  # spans the chart, not just the caption line


def test_describe_uses_describer_and_abstains(sample_fig_page):
    fake = FakeDescriber(ret="Line chart of GDP growth; values not stated in the figure.")
    out = describe_figures(sample_fig_page, [("Figure 1.1", (60, 100, 300, 300))], fake)
    assert isinstance(out[0], FigureContent)
    assert out[0].caption == "Figure 1.1"
    assert out[0].page == sample_fig_page.number
    assert "not stated" in out[0].description
    assert fake.calls[0][0][:8] == b"\x89PNG\r\n\x1a\n"


def test_prompt_demands_labeled_only_and_abstain():
    from app.rag.vision import FIGURE_PROMPT

    assert "not stated in the figure" in FIGURE_PROMPT
    assert "never infer" in FIGURE_PROMPT.lower()
