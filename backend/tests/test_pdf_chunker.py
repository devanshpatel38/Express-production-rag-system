from app.ingestion.pdf_chunker import chunk_document
from app.ingestion.pdf_loader import LoadedDoc, LoadedPage
from app.ingestion.pdf_tables import TableRecord, TableRow


def _table(page=3):
    return TableRecord(
        title="Power consumption", units="W", page=page,
        rows=[
            TableRow("Off", {"100V": "0.27W", "115V": "0.27W", "230V": "0.29W"}),
            TableRow("Sleep", {"100V": "0.5W", "115V": "0.5W", "230V": "0.6W"}),
        ],
    )


def test_prose_windows_overlap_and_metadata():
    para = "Sentence about the iMac display. " * 10  # ~330 chars
    prose = "\n\n".join([para.strip()] * 6)
    doc = LoadedDoc("imac.pdf", [LoadedPage(2, "Environmental", prose, [])])
    chunks = chunk_document(doc, chunk_size=700, chunk_overlap=120)
    assert len(chunks) > 1
    for c in chunks:
        assert c.chunk_type == "prose" and c.page == 2
        assert c.section == "Environmental" and c.units is None and c.table_title is None
        assert c.source_path == "imac.pdf"
    for a, b in zip(chunks, chunks[1:]):
        assert b.char_start < a.char_end  # overlap
        assert b.char_start > a.char_start


def test_section_fallback():
    doc = LoadedDoc("x.pdf", [LoadedPage(5, "", "hello", [])])
    assert chunk_document(doc)[0].section == "Page 5"


def test_table_rows():
    doc = LoadedDoc("imac.pdf", [LoadedPage(3, "Power", "", [_table()])])
    chunks = chunk_document(doc)
    assert len(chunks) == 2
    c = chunks[0]
    assert c.text.startswith("[Table: Power consumption | units: W | page 3]")
    assert "Off: 100V=0.27W; 115V=0.27W; 230V=0.29W" in c.text
    assert (c.chunk_type, c.units, c.table_title, c.page, c.section) == (
        "table_row", "W", "Power consumption", 3, "Power")
    assert "Sleep" in chunks[1].text


def test_ids_unique_and_stable():
    doc = LoadedDoc("imac.pdf", [
        LoadedPage(3, "Power", "Some prose.\n\nMore prose.", [_table()]),
        LoadedPage(4, "Other", "Other prose.", []),
    ])
    ids = [c.chunk_id for c in chunk_document(doc)]
    assert len(ids) == len(set(ids)) == 4
    assert ids == [c.chunk_id for c in chunk_document(doc)]


def test_empty_prose_no_chunk():
    doc = LoadedDoc("imac.pdf", [LoadedPage(1, "S", "   \n ", [])])
    assert chunk_document(doc) == []
