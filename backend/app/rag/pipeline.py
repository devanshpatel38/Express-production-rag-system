"""The RAG pipeline: retrieve -> rerank -> generate.

A straight line, no loops. Each stage's output is exposed on PipelineResult so
the eval harness can inspect pre/post-rerank candidates.
"""
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
    # page/units/chunk_type are read defensively: the Candidate dataclass only
    # gains these fields in a later task.
    return [
        Source(
            chunk_id=c.chunk_id,
            source_path=c.source_path,
            title=c.title,
            snippet=_snippet(c.text),
            score=round(c.score, 4),
            page=getattr(c, "page", None),
            units=getattr(c, "units", "") or None,
            chunk_type=getattr(c, "chunk_type", "prose"),
        )
        for c in candidates
    ]


@dataclass
class PipelineResult:
    answer: str
    sources: list[Source]
    latency_ms: int
    # Useful in eval mode - we expose what each stage produced.
    pre_rerank: list[Candidate] = field(default_factory=list)
    post_rerank: list[Candidate] = field(default_factory=list)


def retrieve_and_rerank(
    query: str,
    top_k: int | None = None,
    use_reranker: bool | None = None,
) -> tuple[list[Candidate], list[Candidate]]:
    """Return (all_candidates, kept_for_generation)."""
    s = get_settings()
    target_k = top_k or s.top_k_rerank
    do_rerank = s.reranker_enabled if use_reranker is None else use_reranker

    candidates = get_retriever().retrieve(query)
    reranker = get_reranker() if do_rerank else None
    if reranker is not None and reranker.enabled:
        kept = reranker.rerank(query, candidates, target_k)
    else:
        kept = candidates[:target_k]
    return candidates, kept


def run_pipeline(
    query: str,
    history: list[ChatMessage] | None = None,
    top_k: int | None = None,
    use_reranker: bool | None = None,
) -> PipelineResult:
    """Synchronous pipeline. Used by /chat and the eval harness."""
    started = time.perf_counter()
    candidates, kept = retrieve_and_rerank(query, top_k, use_reranker)
    answer = get_generator().generate(query, kept, history or [])
    return PipelineResult(
        answer=answer,
        sources=_sources_from(kept),
        latency_ms=int((time.perf_counter() - started) * 1000),
        pre_rerank=candidates[: get_settings().top_k_dense],
        post_rerank=kept,
    )
