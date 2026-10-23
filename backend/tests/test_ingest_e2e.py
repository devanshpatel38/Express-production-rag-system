"""End-to-end ingest of the real GPO PDF (first 85 pages) into a temp index.

Offline: the embedder is a deterministic fake; BM25 carries the keyword query.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from app.config import Settings
from app.ingestion import indexer
from app.rag import retriever
from scripts import ingest

PDF = Path(__file__).resolve().parents[2] / "GPO-Anual-report.pdf"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not PDF.exists(), reason="GPO-Anual-report.pdf not present"),
]

DIM = 8
TABLE_PAGE_1BASED = 81


class FakeEmbedder:
    dim = DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            digest = hashlib.sha256(t.encode("utf-8")).digest()
            vec = [b / 255.0 + 0.01 for b in digest[:DIM]]
            norm = math.sqrt(sum(v * v for v in vec))
            out.append([v / norm for v in vec])
        return out


def test_ingest_builds_searchable_index(monkeypatch, tmp_path):
    settings = Settings(
        chroma_path=str(tmp_path / "chroma"),
        bm25_index_path=str(tmp_path / "bm25.pkl"),
        docs_meta_path=str(tmp_path / "docs_meta.json"),
        collection_name="test_ingest_e2e",
        hybrid_alpha=0.5,
        top_k_dense=15,
        top_k_bm25=15,
    )
    fake = FakeEmbedder()
    for mod in (ingest, indexer, retriever):
        monkeypatch.setattr(mod, "get_settings", lambda: settings)
    monkeypatch.setattr("app.rag.embeddings.get_embedder", lambda: fake)
    monkeypatch.setattr(indexer, "get_embedder", lambda: fake)
    monkeypatch.setattr(retriever, "get_embedder", lambda: fake)

    ingest.run_ingest(str(PDF), max_pages=85)

    meta = json.loads(Path(settings.docs_meta_path).read_text(encoding="utf-8"))
    rows = [
        m for m in meta.values()
        if m["chunk_type"] == "table_row" and m["units"] and m["source_path"] == "GPO-Anual-report.pdf"
    ]
    assert rows, "expected table_row chunks with units and basename source_path"

    cands = retriever.HybridRetriever().retrieve("Department of State billings 2018")
    hits = [
        c for c in cands
        if c.page == TABLE_PAGE_1BASED and c.chunk_type == "table_row"
    ]
    assert hits, f"no page-{TABLE_PAGE_1BASED} table_row candidate in {[(c.page, c.chunk_type) for c in cands]}"
