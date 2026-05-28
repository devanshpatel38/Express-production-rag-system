"""Pipeline glue. Keeping this thin so each stage stays independently testable."""
from __future__ import annotations

import time
from dataclasses import dataclass

from app.config import get_settings
from app.models.schemas import ChatMessage, Source
from app.rag.generator import get_generator
from app.rag.reranker import get_reranker
from app.rag.retriever import Candidate, get_retriever


@dataclass
class PipelineResult:
    answer: str
    sources: list[Source]
    latency_ms: int
    # Useful in eval mode - we expose what each stage produced.
    pre_rerank: list[Candidate]
    post_rerank: list[Candidate]


def _snippet(text: str, n: int = 220) -> str:
    text = " ".join(text.split())  # collapse whitespace for a clean preview
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def run_pipeline(
    query: str,
    history: list[ChatMessage] | None = None,
    top_k: int | None = None,
    use_reranker: bool | None = None,
) -> PipelineResult:
    s = get_settings()
    history = history or []
    target_k = top_k or s.top_k_rerank
    do_rerank = s.reranker_enabled if use_reranker is None else use_reranker

    started = time.perf_counter()

    retriever = get_retriever()
    candidates = retriever.retrieve(query)

    if do_rerank:
        reranker = get_reranker()
        top = reranker.rerank(query, candidates, target_k) if reranker.enabled else candidates[:target_k]
    else:
        top = candidates[:target_k]

    generator = get_generator()
    answer = generator.generate(query, top, history)

    sources = [
        Source(
            chunk_id=c.chunk_id,
            source_path=c.source_path,
            title=c.title,
            snippet=_snippet(c.text),
            score=round(c.score, 4),
        )
        for c in top
    ]
    latency_ms = int((time.perf_counter() - started) * 1000)
    return PipelineResult(
        answer=answer,
        sources=sources,
        latency_ms=latency_ms,
        pre_rerank=candidates[: s.top_k_dense],  # cap for the eval payload
        post_rerank=top,
    )
