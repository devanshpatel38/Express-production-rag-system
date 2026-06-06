"""The self-healing RAG pipeline.

Naive RAG is a straight line: retrieve -> rerank -> generate. This pipeline
treats that line as a *hypothesis* that needs to survive inspection. The shape:

  ┌─────────────────────────────────────────────────────────────┐
  │  1. Adaptive routing      (off-topic? short-circuit early)  │
  │  2. Semantic cache lookup (paraphrase of a recent query?)   │
  │ ┌─ LOOP (bounded by max_healing_attempts) ─────────────────┐│
  │ │  3. (optional) HyDE: embed a hypothetical answer        ││
  │ │  4. Hybrid retrieve + rerank                            ││
  │ │  5. LLM grades each chunk; weak ones get dropped        ││
  │ │  6. If too few survived -> rewrite query + retry        ││
  │ │  7. Generate answer from surviving chunks               ││
  │ │  8. Faithfulness check; if low -> rewrite + retry       ││
  │ └──────────────────────────────────────────────────────────┘│
  │  9. Cache the final answer, return with trace               │
  └─────────────────────────────────────────────────────────────┘

Every stage appends a HealingEvent so the UI can render exactly what happened.
This is the demo hook - most online tutorials hide the loop behind a black box.

A legacy "naive" path is still available when self_healing_enabled=False, so
the eval harness can A/B the two modes for a portfolio screenshot.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Iterator

from app.config import get_settings
from app.models.schemas import ChatMessage, HealingEvent, Source
from app.rag.cache import get_cache
from app.rag.generator import get_generator
from app.rag.grader import get_grader
from app.rag.query_rewriter import get_rewriter
from app.rag.reranker import get_reranker
from app.rag.retriever import Candidate, get_retriever
from app.rag.router import OFF_TOPIC_REPLY, get_router
from app.rag.verifier import FALLBACK_ANSWER, get_verifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        )
        for c in candidates
    ]


@dataclass
class PipelineResult:
    answer: str
    sources: list[Source]
    latency_ms: int
    trace: list[HealingEvent] = field(default_factory=list)
    from_cache: bool = False
    fallback: bool = False
    attempts: int = 1
    # Useful in eval mode - we expose what each stage produced.
    pre_rerank: list[Candidate] = field(default_factory=list)
    post_rerank: list[Candidate] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Legacy path (preserved so the eval harness can A/B against self-healing)
# ---------------------------------------------------------------------------

def _run_naive(
    query: str,
    history: list[ChatMessage],
    target_k: int,
    do_rerank: bool,
) -> PipelineResult:
    started = time.perf_counter()
    retriever = get_retriever()
    candidates = retriever.retrieve(query)

    if do_rerank:
        reranker = get_reranker()
        top = reranker.rerank(query, candidates, target_k) if reranker.enabled else candidates[:target_k]
    else:
        top = candidates[:target_k]

    answer = get_generator().generate(query, top, history)

    latency_ms = int((time.perf_counter() - started) * 1000)
    return PipelineResult(
        answer=answer,
        sources=_sources_from(top),
        latency_ms=latency_ms,
        pre_rerank=candidates[: get_settings().top_k_dense],
        post_rerank=top,
    )


# ---------------------------------------------------------------------------
# Self-healing path
# ---------------------------------------------------------------------------

def _retrieve_grade_filter(
    query: str,
    embed_text: str | None,
    target_k: int,
    do_rerank: bool,
    on_event: Callable[[HealingEvent], None],
    attempt: int,
) -> tuple[list[Candidate], list[Candidate], float]:
    """Run retrieval + rerank + grading. Return (top_for_generation, all_candidates, keep_ratio).

    keep_ratio is how many graded chunks cleared the threshold; the caller uses
    it to decide whether to trigger a rewrite.
    """
    s = get_settings()
    retriever = get_retriever()
    candidates = retriever.retrieve(query, embed_text=embed_text)
    on_event(HealingEvent(
        stage="retrieval", attempt=attempt,
        message=f"Hybrid retrieval returned {len(candidates)} candidates",
        detail={"k_dense": s.top_k_dense, "k_bm25": s.top_k_bm25},
    ))

    if do_rerank:
        reranker = get_reranker()
        if reranker.enabled:
            top = reranker.rerank(query, candidates, target_k)
            on_event(HealingEvent(
                stage="rerank", attempt=attempt,
                message=f"Cross-encoder reranker narrowed to top {len(top)}",
            ))
        else:
            top = candidates[:target_k]
    else:
        top = candidates[:target_k]

    if not s.retrieval_grading_enabled or not top:
        return top, candidates, 1.0

    graded = get_grader().grade(query, top)
    kept = [g.candidate for g in graded if g.relevance >= s.grading_keep_threshold]
    ratio = len(kept) / max(1, len(graded))
    avg_score = sum(g.relevance for g in graded) / max(1, len(graded))
    on_event(HealingEvent(
        stage="grading", attempt=attempt,
        message=f"Grader kept {len(kept)}/{len(graded)} chunks (avg score {avg_score:.2f})",
        score=avg_score,
        detail={
            "threshold": s.grading_keep_threshold,
            "per_chunk": [
                {"path": g.candidate.source_path, "score": round(g.relevance, 2), "reason": g.reason}
                for g in graded
            ],
        },
    ))
    return kept, candidates, ratio


def _run_self_healing(
    query: str,
    history: list[ChatMessage],
    target_k: int,
    do_rerank: bool,
    use_hyde: bool,
    on_event: Callable[[HealingEvent], None] | None = None,
) -> PipelineResult:
    s = get_settings()
    trace: list[HealingEvent] = []

    def emit(ev: HealingEvent) -> None:
        trace.append(ev)
        if on_event is not None:
            on_event(ev)

    started = time.perf_counter()

    # --- Step 1: Adaptive routing -------------------------------------------
    # Off-topic queries get cut here without consuming the retrieval budget.
    if s.adaptive_routing_enabled:
        try:
            decision = get_router().route(query)
            emit(HealingEvent(
                stage="routing", attempt=1,
                message=f"Routed as '{decision.intent}'",
                detail={"reason": decision.reason},
            ))
            if decision.intent == "off_topic":
                # Short-circuit. No retrieval, no generation, no LLM bill.
                latency_ms = int((time.perf_counter() - started) * 1000)
                return PipelineResult(
                    answer=OFF_TOPIC_REPLY,
                    sources=[],
                    latency_ms=latency_ms,
                    trace=trace,
                    attempts=1,
                )
            # Ambiguous queries get HyDE forced on - they need the boost.
            if decision.intent == "ambiguous":
                use_hyde = True
        except Exception as e:
            # Router failure should never block the request.
            emit(HealingEvent(stage="routing", attempt=1, message=f"Router failed: {e}; proceeding as 'clear'"))

    # --- Step 2: Semantic cache lookup --------------------------------------
    if s.semantic_cache_enabled:
        cache = get_cache()
        hit = cache.lookup(query)
        if hit:
            payload, sim, matched = hit
            emit(HealingEvent(
                stage="cache_hit", attempt=1,
                message=f"Served from semantic cache (similarity {sim:.2f})",
                score=sim,
                detail={"matched_query": matched},
            ))
            latency_ms = int((time.perf_counter() - started) * 1000)
            return PipelineResult(
                answer=payload["answer"],
                sources=[Source(**src) for src in payload["sources"]],
                latency_ms=latency_ms,
                trace=trace,
                from_cache=True,
                attempts=1,
            )

    # --- Self-healing loop --------------------------------------------------
    current_query = query
    embed_text: str | None = None
    best_attempt: tuple[str, list[Candidate], float] | None = None  # (answer, sources, score)

    for attempt in range(1, s.max_healing_attempts + 1):
        # HyDE: only on attempt 1 if requested, or whenever we have no candidates.
        if use_hyde and s.hyde_enabled and embed_text is None:
            try:
                hypothetical = get_rewriter().hyde(current_query)
                if hypothetical:
                    embed_text = hypothetical
                    emit(HealingEvent(
                        stage="hyde", attempt=attempt,
                        message="Generated hypothetical answer for dense retrieval",
                        detail={"preview": _snippet(hypothetical, 200)},
                    ))
            except Exception as e:
                emit(HealingEvent(stage="hyde", attempt=attempt, message=f"HyDE failed: {e}; using raw query"))

        # Retrieve, rerank, grade.
        kept, all_cands, keep_ratio = _retrieve_grade_filter(
            current_query, embed_text, target_k, do_rerank, emit, attempt
        )

        # If grading wiped out almost everything, try a query rewrite (if we have budget).
        if (
            s.retrieval_grading_enabled
            and keep_ratio < s.grading_min_keep_ratio
            and attempt < s.max_healing_attempts
        ):
            try:
                rewritten = get_rewriter().rewrite(current_query)
            except Exception as e:
                rewritten = ""
                emit(HealingEvent(stage="rewrite", attempt=attempt, message=f"Rewrite failed: {e}"))
            if rewritten and rewritten != current_query:
                emit(HealingEvent(
                    stage="rewrite", attempt=attempt,
                    message="Retrieval graded weak; rewriting query",
                    detail={"from": current_query, "to": rewritten},
                ))
                current_query = rewritten
                embed_text = None  # let HyDE regenerate on the new query if enabled
                emit(HealingEvent(stage="retry", attempt=attempt + 1, message=f"Starting attempt {attempt + 1}"))
                continue

        # Pick what goes into the prompt. If grading nuked everything we still
        # try to answer from the unfiltered top-k - better to say "I don't
        # know from this" than to send an empty prompt.
        context_for_gen = kept if kept else all_cands[:target_k]

        # Generate.
        try:
            answer = get_generator().generate(current_query, context_for_gen, history)
        except Exception as e:
            emit(HealingEvent(stage="generation", attempt=attempt, message=f"Generation failed: {e}"))
            answer = ""
        emit(HealingEvent(
            stage="generation", attempt=attempt,
            message=f"Answer generated ({len(answer.split())} words)",
        ))

        # Faithfulness check.
        if s.faithfulness_check_enabled and answer.strip():
            try:
                fc = get_verifier().verify(current_query, answer, context_for_gen)
            except Exception as e:
                fc = None
                emit(HealingEvent(stage="faithfulness", attempt=attempt, message=f"Verifier failed: {e}"))
            if fc is not None:
                emit(HealingEvent(
                    stage="faithfulness", attempt=attempt,
                    message=f"Faithfulness {fc.score:.2f} ({fc.reason})",
                    score=fc.score,
                    detail={"unsupported": fc.unsupported_claims},
                ))
                # Track best so far for the fail-safe.
                if best_attempt is None or fc.score > best_attempt[2]:
                    best_attempt = (answer, context_for_gen, fc.score)
                if fc.score < s.faithfulness_threshold and attempt < s.max_healing_attempts:
                    # Try a rewrite-and-retry cycle.
                    try:
                        rewritten = get_rewriter().rewrite(current_query)
                    except Exception:
                        rewritten = ""
                    if rewritten and rewritten != current_query:
                        emit(HealingEvent(
                            stage="rewrite", attempt=attempt,
                            message="Faithfulness below threshold; rewriting and retrying",
                            detail={"from": current_query, "to": rewritten},
                        ))
                        current_query = rewritten
                        embed_text = None
                        emit(HealingEvent(stage="retry", attempt=attempt + 1, message=f"Starting attempt {attempt + 1}"))
                        continue
                # Acceptable answer.
                emit(HealingEvent(stage="done", attempt=attempt, message="Answer accepted", score=fc.score))
                latency_ms = int((time.perf_counter() - started) * 1000)
                result = PipelineResult(
                    answer=answer,
                    sources=_sources_from(context_for_gen),
                    latency_ms=latency_ms,
                    trace=trace,
                    attempts=attempt,
                    pre_rerank=all_cands[: s.top_k_dense],
                    post_rerank=context_for_gen,
                )
                if s.semantic_cache_enabled and not result.fallback:
                    get_cache().store(query, {
                        "answer": result.answer,
                        "sources": [src.model_dump() for src in result.sources],
                    })
                return result

        # No faithfulness check ran (disabled or failed); accept this attempt.
        emit(HealingEvent(stage="done", attempt=attempt, message="Answer accepted (no faithfulness check)"))
        latency_ms = int((time.perf_counter() - started) * 1000)
        result = PipelineResult(
            answer=answer,
            sources=_sources_from(context_for_gen),
            latency_ms=latency_ms,
            trace=trace,
            attempts=attempt,
            pre_rerank=all_cands[: s.top_k_dense],
            post_rerank=context_for_gen,
        )
        if s.semantic_cache_enabled:
            get_cache().store(query, {
                "answer": result.answer,
                "sources": [src.model_dump() for src in result.sources],
            })
        return result

    # We exhausted attempts without an accepted answer.
    if best_attempt is not None and best_attempt[2] >= s.faithfulness_threshold * 0.85:
        # Marginal but usable - return it with a fallback flag.
        emit(HealingEvent(stage="give_up", attempt=s.max_healing_attempts, message="Returning best attempt"))
        ans, ctx, score = best_attempt
        latency_ms = int((time.perf_counter() - started) * 1000)
        return PipelineResult(
            answer=ans,
            sources=_sources_from(ctx),
            latency_ms=latency_ms,
            trace=trace,
            fallback=True,
            attempts=s.max_healing_attempts,
            post_rerank=ctx,
        )

    # Truly couldn't ground anything. Return the humble fallback.
    emit(HealingEvent(stage="give_up", attempt=s.max_healing_attempts, message="No grounded answer found; returning fallback"))
    latency_ms = int((time.perf_counter() - started) * 1000)
    return PipelineResult(
        answer=FALLBACK_ANSWER,
        sources=[],
        latency_ms=latency_ms,
        trace=trace,
        fallback=True,
        attempts=s.max_healing_attempts,
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def run_pipeline(
    query: str,
    history: list[ChatMessage] | None = None,
    top_k: int | None = None,
    use_reranker: bool | None = None,
    use_self_healing: bool | None = None,
    use_hyde: bool | None = None,
) -> PipelineResult:
    """Synchronous pipeline. Used by /chat and the eval harness."""
    s = get_settings()
    history = history or []
    target_k = top_k or s.top_k_rerank
    do_rerank = s.reranker_enabled if use_reranker is None else use_reranker
    sh = s.self_healing_enabled if use_self_healing is None else use_self_healing
    hyde = (s.hyde_enabled if use_hyde is None else use_hyde) and sh
    if sh:
        return _run_self_healing(query, history, target_k, do_rerank, hyde, on_event=None)
    return _run_naive(query, history, target_k, do_rerank)


def stream_self_healing(
    query: str,
    history: list[ChatMessage] | None = None,
    top_k: int | None = None,
    use_reranker: bool | None = None,
    use_hyde: bool | None = None,
) -> Iterator[tuple[str, dict]]:
    """SSE-friendly generator. Yields (event_type, payload) tuples.

    Event types:
      - "event"  : HealingEvent dict (a step finished)
      - "token"  : streamed answer fragment
      - "final"  : final ChatResponse-shaped dict (after stream completes)
    """
    s = get_settings()
    history = history or []
    target_k = top_k or s.top_k_rerank
    do_rerank = s.reranker_enabled if use_reranker is None else use_reranker
    hyde = (s.hyde_enabled if use_hyde is None else use_hyde)

    # We run the heavy loop synchronously inside the generator and stream events
    # as they arrive via a side-channel buffer. This is simpler than a full
    # async refactor and works fine inside FastAPI's threadpool.
    buffer: list[tuple[str, dict]] = []

    def on_event(ev: HealingEvent) -> None:
        buffer.append(("event", ev.model_dump()))

    started = time.perf_counter()
    result = _run_self_healing(query, history, target_k, do_rerank, hyde, on_event=on_event)
    # Replay any buffered events to the SSE consumer.
    for item in buffer:
        yield item

    # Stream the final answer token-by-token even though it's already complete -
    # this is fast (string slicing) and keeps the UX consistent with future
    # true-streaming where tokens arrive from the LLM.
    answer = result.answer
    step = 24
    for i in range(0, len(answer), step):
        yield ("token", {"text": answer[i : i + step]})

    yield ("final", {
        "answer": result.answer,
        "sources": [src.model_dump() for src in result.sources],
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "trace": [e.model_dump() for e in result.trace],
        "from_cache": result.from_cache,
        "fallback": result.fallback,
        "attempts": result.attempts,
    })
