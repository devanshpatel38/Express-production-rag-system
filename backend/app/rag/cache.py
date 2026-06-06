"""Semantic cache for repeated / paraphrased queries.

Standard string-key caches miss "How do I make a GET route?" vs "how do you
define a GET endpoint" - same intent, different words. A semantic cache
embeds the query and checks for any past entry within a cosine-similarity
threshold (~0.95).

Design choices:
- In-memory only. Per-process, no Redis dependency, dies on restart. That's
  fine for a portfolio demo; for prod, swap the dict for a Redis vectorset.
- LRU eviction by recency. Simple ordered dict.
- We cache the FINAL ChatResponse-shaped payload, including sources and trace.
  The trace gets a synthetic "cache_hit" event prepended when we return.
- Cache hits are *not* eligible for self-healing (we already healed once).
  This matters because the cached answer may have been a fallback.

Thread-safety: FastAPI runs sync request handlers in a threadpool, so concurrent
reads/writes are possible. We use a single lock; the cost is negligible vs an
LLM call. If contention ever shows up (it won't at any realistic QPS for this
app) we'd switch to a sharded cache.
"""
from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.rag.embeddings import get_embedder


@dataclass
class _Entry:
    embedding: list[float]
    query: str
    payload: dict[str, Any]   # serialised ChatResponse minus volatile fields
    created_at: float


def _cosine(a: list[float], b: list[float]) -> float:
    # Embeddings from our local model are unit-normalized (see embeddings.py),
    # so cosine == dot product. We don't assume that here - cheap to be safe.
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class SemanticCache:
    def __init__(self, max_size: int, threshold: float) -> None:
        self._max = max_size
        self._threshold = threshold
        # OrderedDict gives O(1) recency tracking for LRU eviction.
        self._store: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return len(self._store)

    def lookup(self, query: str) -> tuple[dict[str, Any], float, str] | None:
        """Return (payload, similarity, matched_query) on hit; None on miss."""
        if not self._store:
            return None
        vec = get_embedder().embed([query])[0]
        best: tuple[str, float] | None = None
        with self._lock:
            for key, entry in self._store.items():
                sim = _cosine(vec, entry.embedding)
                if best is None or sim > best[1]:
                    best = (key, sim)
            if best is None or best[1] < self._threshold:
                return None
            key, sim = best
            entry = self._store[key]
            # Touch for LRU.
            self._store.move_to_end(key)
            return (entry.payload, sim, entry.query)

    def store(self, query: str, payload: dict[str, Any]) -> None:
        vec = get_embedder().embed([query])[0]
        with self._lock:
            # Key by exact query; same payload can be reached via many embeddings.
            self._store[query] = _Entry(
                embedding=vec,
                query=query,
                payload=payload,
                created_at=time.time(),
            )
            self._store.move_to_end(query)
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


@lru_cache
def get_cache() -> SemanticCache:
    s = get_settings()
    return SemanticCache(max_size=s.semantic_cache_size, threshold=s.semantic_cache_threshold)
