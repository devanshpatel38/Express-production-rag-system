"""Chat endpoints.

  POST /chat         : synchronous, returns full ChatResponse JSON.
  POST /chat/stream  : Server-Sent Events. Streams answer tokens, then a final
                       payload with sources and latency.
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest, ChatResponse
from app.rag.generator import get_generator
from app.rag.pipeline import _sources_from, retrieve_and_rerank, run_pipeline


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        result = run_pipeline(
            query=req.query,
            history=req.history,
            top_k=req.top_k,
            use_reranker=req.use_reranker,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Index not ready: {e}") from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ChatResponse(answer=result.answer, sources=result.sources, latency_ms=result.latency_ms)


def _sse_format(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE: `token` events (answer fragments), then one `final` event with the
    ChatResponse payload; `error` if something blew up."""

    def gen():
        try:
            started = time.perf_counter()
            _, top = retrieve_and_rerank(req.query, req.top_k, req.use_reranker)
            parts: list[str] = []
            for tok in get_generator().stream(req.query, top, req.history):
                parts.append(tok)
                yield _sse_format("token", {"text": tok})
            final = ChatResponse(
                answer="".join(parts),
                sources=_sources_from(top),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            yield _sse_format("final", final.model_dump())
        except FileNotFoundError as e:
            yield _sse_format("error", {"message": f"Index not ready: {e}"})
        except Exception as e:
            yield _sse_format("error", {"message": str(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
