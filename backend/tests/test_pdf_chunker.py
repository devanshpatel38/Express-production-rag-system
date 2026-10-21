from app.ingestion.pdf_chunker import chunk_pages
from app.ingestion.pdf_figures import FigureContent
from app.ingestion.pdf_loader import PageContent
from app.ingestion.pdf_tables import TableData


def test_table_row_chunk_is_keyvalue_with_units():
    td = TableData(page=100, title="EMDE growth", units="percent", columns=["2026f"],
                   rows=[("Sub-Saharan Africa", {"2026f": "4.0"})], bbox=(0, 0, 0, 0))
    chunks = chunk_pages([PageContent(100, "", [td], [])], 700, 120)
    row = [c for c in chunks if c.chunk_type == "table_row"][0]
    assert "Sub-Saharan Africa" in row.text and "2026f: 4.0" in row.text
    assert row.units == "percent" and row.page == 100
    assert row.table_title == "EMDE growth"
    assert row.text.startswith("[Table: EMDE growth | units: percent | page 100]\n")


def test_page_comes_from_page_content_not_table():
    td = TableData(page=1, title="T", units="", columns=["a"],
                   rows=[("r", {"a": "1"})], bbox=(0, 0, 0, 0))
    fig = FigureContent(1, "Figure 2", "d")
    chunks = chunk_pages([PageContent(42, "", [td], [fig])], 700, 120)
    assert chunks and all(c.page == 42 for c in chunks)


def test_prose_windowing_no_frontmatter_logic():
    long = "para one.\n\n" + "x " * 800
    chunks = chunk_pages([PageContent(5, long, [], [])], 700, 120)
    assert len(chunks) >= 2 and all(c.chunk_type == "prose" for c in chunks)
    assert all(c.page == 5 for c in chunks)


def test_prose_text_starting_with_dashes_is_kept():
    chunks = chunk_pages([PageContent(1, "---\nkey: v\n---\nbody", [], [])], 700, 120)
    assert "key: v" in chunks[0].text


def test_figure_chunk_carries_caption():
    pc = PageContent(7, "", [], [FigureContent(7, "Figure 1.1", "desc")])
    c = [c for c in chunk_pages([pc], 700, 120) if c.chunk_type == "figure"][0]
    assert "Figure 1.1" in c.text and c.page == 7
    assert c.text == "[Figure: Figure 1.1 | page 7] desc"
