"""Embedding backends.

The local sentence-transformers path is the default - keeps dev free and gives
the project a "works offline" story. OpenAI is there for when you actually want
to scale beyond ~100k chunks.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.config import get_settings


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dim(self) -> int: ...


class _LocalEmbedder:
    """sentence-transformers wrapper. Lazy-loaded so the model only downloads
    when we actually need it (keeps cold-start fast for non-ingest endpoints)."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None  # lazy
        self._dim = 384  # MiniLM-L6-v2; will be overwritten on first load

    def _ensure(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
            self._dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._ensure()
        # normalize_embeddings=True gives us unit vectors so cosine == dot product later.
        vecs = self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vecs.tolist()

    @property
    def dim(self) -> int:
        self._ensure()
        return self._dim


class _OpenAIEmbedder:
    def __init__(self, model: str, api_key: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        # text-embedding-3-small is 1536-d. Hardcoded to avoid an extra call on startup.
        self._dim = 1536

    def embed(self, texts: list[str]) -> list[list[float]]:
        # OpenAI handles batching up to ~2048 inputs; we keep batches small to avoid 429s.
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            batch = texts[i : i + 64]
            resp = self._client.embeddings.create(model=self._model, input=batch)
            out.extend(item.embedding for item in resp.data)
        return out

    @property
    def dim(self) -> int:
        return self._dim


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_backend == "openai":
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY missing but embedding_backend=openai")
        return _OpenAIEmbedder(s.openai_embedding_model, s.openai_api_key)
    return _LocalEmbedder(s.local_embedding_model)
