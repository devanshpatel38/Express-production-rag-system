"""Straight RAG pipeline: retrieve -> rerank -> generate."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.config import get_settings
from app.models.schemas import ChatMessage, Source
from app.rag.generator import get_generator
from app.rag.reranker import get_reranker
from app.rag.retriever import Candidate, get_retriever


def _snippet(text: str, n: int = 220) -> str:
    text = " ".join(text.split())  # collapse whitespace for a clean preview
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def _sources_from(candidates: list[Candidate]) -> list[Source]:
    return [
        Source(
            chunk_id=c.chunk_id,
            source_path=c.source_path,
            title=c.title,
            snippet=_snippet(c.text),
            score=round(c.score, 4),
            page=c.page,
            units=c.units,
            chunk_type=c.chunk_type,
        )
        for c in candidates
    ]


@dataclass
class PipelineResult:
    answer: str
    sources: list[Source]
    latency_ms: int
    # Exposed for the eval harness.
    pre_rerank: list[Candidate] = field(default_factory=list)
    post_rerank: list[Candidate] = field(default_factory=list)


def retrieve_and_rerank(
    query: str, top_k: int | None = None, use_reranker: bool | None = None
) -> tuple[list[Candidate], list[Candidate]]:
    s = get_settings()
    target_k = top_k or s.top_k_rerank
    candidates = get_retriever().retrieve(query)
    do_rerank = s.reranker_enabled if use_reranker is None else use_reranker
    if do_rerank:
        top = get_reranker().rerank(query, candidates, target_k)
    else:
        top = candidates[:target_k]
    return candidates, top


def run_pipeline(
    query: str,
    history: list[ChatMessage] | None = None,
    top_k: int | None = None,
    use_reranker: bool | None = None,
) -> PipelineResult:
    started = time.perf_counter()
    history = history or []
    candidates, top = retrieve_and_rerank(query, top_k, use_reranker)
    answer = get_generator().generate(query, top, history)
    return PipelineResult(
        answer=answer,
        sources=_sources_from(top),
        latency_ms=int((time.perf_counter() - started) * 1000),
        pre_rerank=candidates[: get_settings().top_k_dense],
        post_rerank=top,
    )
