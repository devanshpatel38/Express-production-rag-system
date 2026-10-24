"""Round-trip new PDF chunks through the indexer into temp stores, then retrieve."""
import json
import pickle

import pytest

from app.config import Settings
from app.ingestion.pdf_chunker import Chunk


class _FakeEmbedder:
    dim = 8

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.01] * 8
            for i, w in enumerate(("power", "load", "solar", "demand")):
                if w in t.lower():
                    v[i] += 1.0
            out.append(v)
        return out


@pytest.fixture
def stores(tmp_path, monkeypatch):
    s = Settings(
        chroma_path=str(tmp_path / "chroma"),
        bm25_index_path=str(tmp_path / "bm25.pkl"),
        docs_meta_path=str(tmp_path / "docs_meta.json"),
        collection_name="imac_report",
    )
    emb = _FakeEmbedder()
    import app.ingestion.indexer as indexer
    import app.rag.retriever as retriever

    for mod in (indexer, retriever):
        monkeypatch.setattr(mod, "get_settings", lambda: s)
        monkeypatch.setattr(mod, "get_embedder", lambda: emb)
    return s, indexer, retriever


def _chunks():
    return [
        Chunk(chunk_id="d:p3:0", source_path="d.pdf", title="Overview", section="Overview",
              text="Narrative about solar generation and demand.", page=3, chunk_type="prose"),
        Chunk(chunk_id="d:p7:0", source_path="d.pdf", title="Power", section="Power",
              text="[Table: Peak load | units: MW | page 7] Winter: peak=1200",
              page=7, chunk_type="table_row", units="MW", table_title="Peak load"),
        Chunk(chunk_id="d:p9:0", source_path="d.pdf", title="Misc", section="Misc",
              text="Unrelated text about wind.", page=9, chunk_type="prose"),
    ]


def test_round_trip_and_retrieve(stores):
    s, indexer, retriever = stores
    info = indexer.build_indices(_chunks())
    assert info["chunks"] == 3

    with open(s.bm25_index_path, "rb") as f:
        payload = pickle.load(f)
    assert payload["ids"] == ["d:p3:0", "d:p7:0", "d:p9:0"] and "bm25" in payload
    meta = json.load(open(s.docs_meta_path, encoding="utf-8"))
    assert meta["d:p7:0"]["units"] == "MW" and meta["d:p7:0"]["page"] == 7
    assert meta["d:p3:0"]["units"] is None  # sidecar keeps raw record

    import chromadb
    col = chromadb.PersistentClient(path=s.chroma_path).get_collection("imac_report")
    assert col.count() == 3
    m = col.get(ids=["d:p3:0"])["metadatas"][0]
    assert m["units"] == "" and m["table_title"] == "" and m["page"] == 3

    r = retriever.HybridRetriever()
    cands = {c.chunk_id: c for c in r.retrieve("peak load power")}
    t = cands["d:p7:0"]
    assert (t.page, t.units, t.chunk_type, t.table_title) == (7, "MW", "table_row", "Peak load")
    p = cands["d:p3:0"]
    assert (p.page, p.units, p.chunk_type) == (3, "", "prose")
