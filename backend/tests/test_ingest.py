from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts import ingest


def test_ingest_wiring_order(monkeypatch):
    calls = []
    doc = SimpleNamespace(pages=[1, 2])
    chunks = [SimpleNamespace(chunk_type="prose"), SimpleNamespace(chunk_type="table_row")]

    def fake_load(src):
        calls.append(("load", src))
        return doc

    def fake_chunk(d, chunk_size, chunk_overlap):
        calls.append(("chunk", d))
        return chunks

    def fake_build(c):
        calls.append(("build", c))
        return {"chunks": len(c)}

    monkeypatch.setattr(ingest, "load_pdf", fake_load)
    monkeypatch.setattr(ingest, "chunk_document", fake_chunk)
    monkeypatch.setattr(ingest, "build_indices", fake_build)

    out = ingest.run("x.pdf")

    assert [c[0] for c in calls] == ["load", "chunk", "build"]
    assert calls[0][1] == "x.pdf"
    assert calls[1][1] is doc
    assert calls[2][1] is chunks
    assert out == {"chunks": 2}
