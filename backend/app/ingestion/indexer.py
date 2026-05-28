"""Builds and persists the two indices we need: Chroma for vectors, BM25 for lexical.

We deliberately keep BM25 in-process (rank_bm25) instead of using Elasticsearch
- the corpus is small (~few thousand chunks) and the deploy stays one container.
"""
from __future__ import annotations

import json
import os
import pickle
import re
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.ingestion.chunker import Chunk
from app.rag.embeddings import get_embedder


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> list[str]:
    # Lowercase + alphanumeric tokens. Good enough for code-heavy docs;
    # a real Lucene analyzer would be overkill here.
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _chroma_client(path: str) -> chromadb.PersistentClient:
    os.makedirs(path, exist_ok=True)
    return chromadb.PersistentClient(path=path)


def build_indices(chunks: list[Chunk]) -> dict:
    """Embed chunks into Chroma and build a parallel BM25 index on disk."""
    s = get_settings()
    if not chunks:
        raise ValueError("No chunks supplied - did ingestion find any markdown files?")

    embedder = get_embedder()
    client = _chroma_client(s.chroma_path)

    # Wipe and recreate so reingest is deterministic.
    try:
        client.delete_collection(s.collection_name)
    except Exception:
        pass
    collection = client.create_collection(s.collection_name, metadata={"hnsw:space": "cosine"})

    ids = [c.chunk_id for c in chunks]
    texts = [c.text for c in chunks]
    metadatas = [
        {
            "source_path": c.source_path,
            "title": c.title,
            "section": c.section,
            "char_start": c.char_start,
            "char_end": c.char_end,
        }
        for c in chunks
    ]

    # Embed in batches so we can show progress on large corpora.
    BATCH = 64
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        embeddings.extend(embedder.embed(texts[i : i + BATCH]))
        print(f"  embedded {min(i + BATCH, len(texts))}/{len(texts)}")

    collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)

    # BM25 lives next to the vector store.
    tokenized = [tokenize(t) for t in texts]
    bm25 = BM25Okapi(tokenized)
    Path(s.bm25_index_path).parent.mkdir(parents=True, exist_ok=True)
    with open(s.bm25_index_path, "wb") as f:
        pickle.dump({"bm25": bm25, "ids": ids, "tokenized": tokenized}, f)

    # We keep a side-car json so the API can hydrate chunk metadata cheaply
    # without going to Chroma for every retrieval.
    meta_index = {c.chunk_id: c.to_dict() for c in chunks}
    with open(s.docs_meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_index, f)

    return {
        "chunks": len(chunks),
        "vector_dim": embedder.dim,
        "chroma_path": s.chroma_path,
        "bm25_path": s.bm25_index_path,
    }
