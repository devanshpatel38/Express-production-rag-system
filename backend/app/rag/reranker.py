"""Cross-encoder reranking via Cohere Rerank.

The hybrid retriever optimises for recall (cast a wide net). The reranker
optimises for precision (which of these 20 actually answer the question).
Cohere's hosted model is the simplest path; swap to a local cross-encoder
(e.g. BAAI/bge-reranker-base) if you ever go off-network.

If COHERE_API_KEY isn't set we fall back to the hybrid score - the system
keeps working, just with worse top-k precision. This makes the project
easy to clone-and-run.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.rag.retriever import Candidate


class _PassthroughReranker:
    enabled = False

    def rerank(self, query: str, candidates: list[Candidate], top_k: int) -> list[Candidate]:
        return candidates[:top_k]


class _CohereReranker:
    enabled = True

    def __init__(self, api_key: str, model: str) -> None:
        import cohere

        self._client = cohere.ClientV2(api_key=api_key)
        self._model = model

    def rerank(self, query: str, candidates: list[Candidate], top_k: int) -> list[Candidate]:
        if not candidates:
            return []
        docs = [c.text for c in candidates]
        resp = self._client.rerank(model=self._model, query=query, documents=docs, top_n=top_k)
        out: list[Candidate] = []
        for r in resp.results:
            c = candidates[r.index]
            # Overwrite score with the rerank relevance - it's a much better signal
            # than the hybrid score for the final ordering.
            out.append(
                Candidate(
                    chunk_id=c.chunk_id,
                    text=c.text,
                    source_path=c.source_path,
                    title=c.title,
                    section=c.section,
                    score=float(r.relevance_score),
                )
            )
        return out


@lru_cache
def get_reranker():
    s = get_settings()
    if s.reranker_enabled and s.cohere_api_key:
        return _CohereReranker(s.cohere_api_key, s.cohere_rerank_model)
    return _PassthroughReranker()
