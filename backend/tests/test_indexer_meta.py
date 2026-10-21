import hashlib

import chromadb

from app.ingestion import indexer
from app.ingestion.chunker import Chunk
from app.rag import retriever as retriever_mod


class FakeEmbedder:
    dim = 8

    def embed(self, texts):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            out.append([(b + 1) / 256.0 for b in h[:8]])
        return out


def _chunk(i, text, **kw):
    return Chunk(
        chunk_id=f"c{i}", source_path="gep.pdf", title="T", section="S",
        text=text, char_start=0, char_end=len(text), **kw,
    )


def test_metadata_roundtrip(tmp_path, monkeypatch):
    s = indexer.get_settings().model_copy(update={
        "chroma_path": str(tmp_path / "chroma"),
        "bm25_index_path": str(tmp_path / "bm25.pkl"),
        "docs_meta_path": str(tmp_path / "docs_meta.json"),
        "collection_name": "test_meta_roundtrip",
    })
    fake = FakeEmbedder()
    monkeypatch.setattr(indexer, "get_settings", lambda: s)
    monkeypatch.setattr(retriever_mod, "get_settings", lambda: s)
    monkeypatch.setattr(indexer, "get_embedder", lambda: fake)
    monkeypatch.setattr(retriever_mod, "get_embedder", lambda: fake)

    chunks = [
        _chunk(1, "Global growth slowed sharply this year", page=12),
        _chunk(2, "GDP growth advanced economies 2.1", page=100,
               chunk_type="table_row", table_title="Growth table", units="percent"),
        _chunk(3, "Figure shows commodity prices", page=7, chunk_type="figure"),
    ]
    indexer.build_indices(chunks)

    col = chromadb.PersistentClient(path=s.chroma_path).get_collection(s.collection_name)
    metas = col.get(include=["metadatas"])["metadatas"]
    assert len(metas) == 3
    for m in metas:
        assert all(v is not None for v in m.values())
        for k in ("page", "chunk_type", "table_title", "units"):
            assert k in m

    cands = retriever_mod.HybridRetriever().retrieve("GDP growth advanced economies")
    row = next(c for c in cands if c.chunk_id == "c2")
    assert row.page == 100
    assert row.units == "percent"
    assert row.chunk_type == "table_row"
    assert "page" in row.to_dict()
