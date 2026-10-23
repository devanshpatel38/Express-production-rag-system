"""Roundtrip: page/units/chunk_type survive build_indices -> HybridRetriever.retrieve.

Offline and fast: the embedder is a fake deterministic 8-dim embedder, and all
settings paths point into pytest's tmp_path.
"""
from __future__ import annotations

import hashlib
import json
import math

import pytest

from app.config import Settings
from app.ingestion import indexer
from app.ingestion.chunker import Chunk
from app.rag import retriever


DIM = 8


class FakeEmbedder:
    dim = DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            digest = hashlib.sha256(t.encode("utf-8")).digest()
            vec = [b / 255.0 + 0.01 for b in digest[:DIM]]  # strictly positive, non-zero
            norm = math.sqrt(sum(v * v for v in vec))
            out.append([v / norm for v in vec])
        return out


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        chroma_path=str(tmp_path / "chroma"),
        bm25_index_path=str(tmp_path / "bm25.pkl"),
        docs_meta_path=str(tmp_path / "docs_meta.json"),
        collection_name="test_gpo_meta",
        hybrid_alpha=0.5,
        top_k_dense=15,
        top_k_bm25=15,
    )


@pytest.fixture
def chunks() -> list[Chunk]:
    return [
        Chunk(
            chunk_id="prose-1",
            source_path="gpo.pdf",
            title="Overview",
            section="Overview",
            text="The annual report describes the organization and its mission.",
            char_start=0,
            char_end=60,
            page=3,
        ),
        Chunk(
            chunk_id="table-1",
            source_path="gpo.pdf",
            title="Revenue",
            section="Financials > Revenue",
            text="Net revenue for fiscal 2025 was reported in the revenue table.",
            char_start=0,
            char_end=64,
            page=80,
            chunk_type="table_row",
            table_title="Statement of Revenue",
            units="dollars in thousands",
        ),
        Chunk(
            chunk_id="prose-2",
            source_path="gpo.pdf",
            title="Governance",
            section="Governance",
            text="The board of directors meets quarterly to review operations.",
            char_start=0,
            char_end=60,
            page=0,  # unknown page
        ),
    ]


@pytest.fixture
def wired(monkeypatch, settings):
    fake = FakeEmbedder()
    monkeypatch.setattr(indexer, "get_settings", lambda: settings)
    monkeypatch.setattr(retriever, "get_settings", lambda: settings)
    monkeypatch.setattr(indexer, "get_embedder", lambda: fake)
    monkeypatch.setattr(retriever, "get_embedder", lambda: fake)
    return settings


def test_roundtrip_exposes_page_and_units_on_candidate(wired, chunks):
    indexer.build_indices(chunks)

    r = retriever.HybridRetriever()
    cands = r.retrieve("revenue dollars thousands")

    by_id = {c.chunk_id: c for c in cands}
    assert "table-1" in by_id
    table = by_id["table-1"]
    assert table.page == 80
    assert table.units == "dollars in thousands"
    assert table.chunk_type == "table_row"


def test_no_chroma_metadata_value_is_none(wired, chunks):
    import chromadb

    # Include a chunk whose optional fields are None to exercise coercion.
    chunks.append(
        Chunk(
            chunk_id="none-1",
            source_path="gpo.pdf",
            title="T",
            section="S",
            text="content with missing optional fields",
            char_start=0,
            char_end=10,
            page=None,  # type: ignore[arg-type]
            chunk_type=None,  # type: ignore[arg-type]
            table_title=None,  # type: ignore[arg-type]
            units=None,  # type: ignore[arg-type]
        )
    )
    indexer.build_indices(chunks)

    client = chromadb.PersistentClient(path=wired.chroma_path)
    coll = client.get_collection(wired.collection_name)
    got = coll.get(include=["metadatas"])
    assert len(got["metadatas"]) == len(chunks)
    for meta in got["metadatas"]:
        for k, v in meta.items():
            assert v is not None, f"Chroma metadata {k!r} is None"
            assert isinstance(v, (str, int, float, bool)), f"{k!r} has type {type(v)}"

    none_meta = next(m for m, i in zip(got["metadatas"], got["ids"]) if i == "none-1")
    assert none_meta["page"] == 0
    assert none_meta["units"] == ""
    assert none_meta["chunk_type"] == ""
    assert none_meta["table_title"] == ""


def test_docs_meta_sidecar_carries_new_fields(wired, chunks):
    indexer.build_indices(chunks)
    with open(wired.docs_meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["table-1"]["page"] == 80
    assert meta["table-1"]["units"] == "dollars in thousands"
    assert meta["table-1"]["chunk_type"] == "table_row"
    assert meta["table-1"]["table_title"] == "Statement of Revenue"
