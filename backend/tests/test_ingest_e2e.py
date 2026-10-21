import hashlib
import json
import os

import pytest

from app.ingestion import indexer
from app.rag import retriever as retriever_mod

PDF = os.path.join(os.path.dirname(__file__), "..", "..", "GEP-Jun-2026.pdf")


class FakeEmbedder:
    dim = 8

    def embed(self, texts):
        return [
            [(b + 1) / 256.0 for b in hashlib.sha256(t.encode()).digest()[:8]]
            for t in texts
        ]


@pytest.mark.integration
@pytest.mark.skipif(not os.path.exists(PDF), reason="GEP PDF not present")
def test_build_small_index(tmp_path, monkeypatch):
    from scripts import ingest

    s = indexer.get_settings().model_copy(update={
        "chroma_path": str(tmp_path / "chroma"),
        "bm25_index_path": str(tmp_path / "bm25.pkl"),
        "docs_meta_path": str(tmp_path / "docs_meta.json"),
        "collection_name": "test_ingest_e2e",
    })
    fake = FakeEmbedder()
    monkeypatch.setattr(indexer, "get_settings", lambda: s)
    monkeypatch.setattr(ingest, "get_settings", lambda: s)
    monkeypatch.setattr(retriever_mod, "get_settings", lambda: s)
    monkeypatch.setattr(indexer, "get_embedder", lambda: fake)
    monkeypatch.setattr(retriever_mod, "get_embedder", lambda: fake)

    counts = ingest.run_ingest(PDF, max_pages=101, no_vision=True)
    assert counts.get("table_row", 0) >= 1

    with open(s.docs_meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    rows = [
        m for m in meta.values()
        if m["chunk_type"] == "table_row" and m["units"]
        and m["source_path"] == "GEP-Jun-2026.pdf"
    ]
    assert rows

    cands = retriever_mod.HybridRetriever().retrieve("Sub-Saharan Africa GDP growth 2026")
    assert any(c.page == 101 and c.chunk_type == "table_row" for c in cands)
