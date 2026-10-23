from app.ingestion.pdf_chunker import chunk_pages
from app.ingestion.pdf_loader import PageContent
from app.ingestion.pdf_tables import TableData


def _table(page=1):
    return TableData(
        page=page,
        title="Obligations by Agency",
        units="in thousands",
        columns=["2018", "2019"],
        rows=[("U.S. Department of State", {"2018": "$ 270,596", "2019": "$ 281,000"})],
    )


def test_table_row_chunk_is_key_value_with_units():
    pc = PageContent(page=7, prose_text="", tables=[_table()], section="Budget")
    chunks = chunk_pages([pc], 700, 120)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.chunk_type == "table_row"
    assert c.text.startswith("[Table: Obligations by Agency | units: in thousands | page 7]")
    assert "U.S. Department of State" in c.text
    assert "2018: $ 270,596" in c.text
    assert "2019: $ 281,000" in c.text
    assert c.units == "in thousands"
    assert c.table_title == "Obligations by Agency"
    assert c.page == 7
    assert c.to_dict()["chunk_type"] == "table_row"


def test_page_comes_from_page_content_not_table_data():
    pc = PageContent(page=42, prose_text="", tables=[_table(page=1)])
    chunks = chunk_pages([pc], 700, 120)
    assert chunks and all(c.page == 42 for c in chunks)
    assert "page 42" in chunks[0].text


def test_prose_windowing_multiple_chunks():
    text = ("Sentence about the budget. " * 20 + "\n\n") * 6
    pc = PageContent(page=3, prose_text=text, section="Overview")
    chunks = chunk_pages([pc], 300, 50)
    assert len(chunks) > 1
    assert all(c.chunk_type == "prose" for c in chunks)
    assert all(c.page == 3 for c in chunks)
    assert all(c.section == "Overview" and c.title == "Overview" for c in chunks)


def test_prose_section_falls_back_to_page_and_no_frontmatter_stripping():
    pc = PageContent(page=5, prose_text="---\nkey: v\n---\nBody text", section=None)
    chunks = chunk_pages([pc], 700, 120)
    assert len(chunks) == 1
    assert chunks[0].section == "Page 5"
    assert chunks[0].text.startswith("---")


def test_empty_prose_yields_no_chunks():
    assert chunk_pages([PageContent(page=1, prose_text="  \n ")], 700, 120) == []
