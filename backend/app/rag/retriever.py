"""Hybrid retrieval: dense (Chroma + cosine) fused with sparse (BM25).

Why both: dense embeddings handle paraphrase ("how do I read query params" matches
"req.query"), BM25 nails exact tokens (method names, error codes). The intersection
is small, the union is what we want.

Fusion scheme: min-max normalize each list to [0, 1], then weighted sum. RRF is
the other popular choice; both work, weighted sum lets us expose a single
`alpha` knob on the API which is great for the demo.

HyDE support: `embed_text` lets the caller pass a different string for the dense
leg (typically a HyDE-generated hypothetical answer) while keeping the original
query for BM25. BM25 needs the user's actual tokens to find verbatim matches;
HyDE only helps the semantic leg.
"""
from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from functools import lru_cache

import chromadb

from app.config import get_settings
from app.ingestion.indexer import tokenize
from app.rag.embeddings import get_embedder


@dataclass
class Candidate:
    chunk_id: str
    text: str
    source_path: str
    title: str
    section: str
    score: float  # fused score after normalization

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "source_path": self.source_path,
            "title": self.title,
            "section": self.section,
            "score": self.score,
        }


def _minmax(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


class HybridRetriever:
    """Holds references to both indices. Built once at app startup."""

    def __init__(self) -> None:
        s = get_settings()
        self._s = s
        client = chromadb.PersistentClient(path=s.chroma_path)
        self._collection = client.get_or_create_collection(s.collection_name)

        with open(s.bm25_index_path, "rb") as f:
            payload = pickle.load(f)
        self._bm25 = payload["bm25"]
        self._bm25_ids: list[str] = payload["ids"]

        with open(s.docs_meta_path, encoding="utf-8") as f:
            self._meta: dict[str, dict] = json.load(f)

        self._embedder = get_embedder()

    @property
    def n_chunks(self) -> int:
        return len(self._bm25_ids)

    def _dense_search(self, embed_text: str, k: int) -> dict[str, float]:
        vec = self._embedder.embed([embed_text])[0]
        res = self._collection.query(query_embeddings=[vec], n_results=k)
        ids = res["ids"][0]
        # Chroma returns cosine *distance* in [0, 2]; flip to similarity.
        dists = res["distances"][0]
        return {cid: 1.0 - d for cid, d in zip(ids, dists)}

    def _bm25_search(self, query: str, k: int) -> dict[str, float]:
        tokens = tokenize(query)
        if not tokens:
            return {}
        raw = self._bm25.get_scores(tokens)
        # Pull top-k by index then map back to chunk ids.
        ranked = sorted(enumerate(raw), key=lambda kv: kv[1], reverse=True)[:k]
        return {self._bm25_ids[i]: float(score) for i, score in ranked if score > 0}

    def retrieve(
        self,
        query: str,
        alpha: float | None = None,
        embed_text: str | None = None,
    ) -> list[Candidate]:
        """Return fused candidates, ranked by combined score.

        `alpha`      : weight on dense (1 - alpha goes to BM25). Lets us A/B
                       pure-vector vs pure-keyword vs blend without redeploys.
        `embed_text` : optional override for the dense leg. Pass a HyDE-generated
                       passage here while leaving `query` as the user's original
                       string for BM25.
        """
        s = self._s
        a = s.hybrid_alpha if alpha is None else alpha

        dense = self._dense_search(embed_text or query, s.top_k_dense)
        sparse = self._bm25_search(query, s.top_k_bm25)

        d_norm = _minmax(dense)
        s_norm = _minmax(sparse)

        fused: dict[str, float] = {}
        for cid in set(d_norm) | set(s_norm):
            fused[cid] = a * d_norm.get(cid, 0.0) + (1 - a) * s_norm.get(cid, 0.0)

        ranked_ids = sorted(fused, key=lambda c: fused[c], reverse=True)
        out: list[Candidate] = []
        for cid in ranked_ids:
            m = self._meta.get(cid)
            if not m:
                continue
            out.append(
                Candidate(
                    chunk_id=cid,
                    text=m["text"],
                    source_path=m["source_path"],
                    title=m["title"],
                    section=m["section"],
                    score=fused[cid],
                )
            )
        return out


@lru_cache
def get_retriever() -> HybridRetriever:
    return HybridRetriever()
