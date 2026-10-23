"""Straight RAG pipeline: retrieve -> rerank -> generate."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterator

from app.config import get_settings
from app.models.schemas import ChatMessage, Source
from app.rag.generator import get_generator
from app.rag.reranker import get_reranker
from app.rag.retriever import Candidate, get_retriever


def _snippet(text: str, n: int = 220) -> str:
    text = " ".join(text.split())  # collapse whitespace for a clean preview
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def _sources_from(candidates: list[Candidate]) -> list[Source]:
    # page/units/chunk_type are read defensively: they are added to Candidate later.
    return [
        Source(
            chunk_id=c.chunk_id,
            source_path=c.source_path,
            title=c.title,
            snippet=_snippet(c.text),
            score=round(c.score, 4),
            page=getattr(c, "page", None),
            units=getattr(c, "units", ""),
            chunk_type=getattr(c, "chunk_type", "prose"),
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


def run_pipeline(
    query: str,
    history: list[ChatMessage] | None = None,
    top_k: int | None = None,
    use_reranker: bool | None = None,
) -> PipelineResult:
    """Synchronous pipeline. Used by /chat and the eval harness."""
    s = get_settings()
    history = history or []
    target_k = top_k or s.top_k_rerank
    do_rerank = s.reranker_enabled if use_reranker is None else use_reranker

    started = time.perf_counter()
    candidates = get_retriever().retrieve(query)

    if do_rerank:
        reranker = get_reranker()
        top = reranker.rerank(query, candidates, target_k) if reranker.enabled else candidates[:target_k]
    else:
        top = candidates[:target_k]

    answer = get_generator().generate(query, top, history)
    return PipelineResult(
        answer=answer,
        sources=_sources_from(top),
        latency_ms=int((time.perf_counter() - started) * 1000),
        pre_rerank=candidates[: s.top_k_dense],
        post_rerank=top,
    )


def stream_pipeline(
    query: str,
    history: list[ChatMessage] | None = None,
    top_k: int | None = None,
    use_reranker: bool | None = None,
) -> Iterator[tuple[str, dict]]:
    """Yields ("token", {text}) fragments, then one ("final", {...})."""
    started = time.perf_counter()
    result = run_pipeline(query, history, top_k, use_reranker)
    answer = result.answer
    step = 24
    for i in range(0, len(answer), step):
        yield ("token", {"text": answer[i : i + step]})
    yield ("final", {
        "answer": answer,
        "sources": [src.model_dump() for src in result.sources],
        "latency_ms": int((time.perf_counter() - started) * 1000),
    })
