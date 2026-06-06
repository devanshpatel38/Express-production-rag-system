"""Chat endpoints.

  POST /chat         : synchronous, returns full ChatResponse JSON.
                       Used by the eval harness and by clients that don't want SSE.
  POST /chat/stream  : Server-Sent Events. Emits healing events as they happen,
                       then streams the answer token-by-token, then a final
                       payload with sources and the full trace.

Both share the same request schema. The SSE endpoint always runs the self-healing
pipeline (streaming the naive path adds complexity for no real benefit).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest, ChatResponse
from app.rag.pipeline import run_pipeline, stream_self_healing
from app.rag.idle_manager import record_request


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    record_request()  # reset idle timer on every request
    try:
        result = run_pipeline(
            query=req.query,
            history=req.history,
            top_k=req.top_k,
            use_reranker=req.use_reranker,
            use_self_healing=req.use_self_healing,
            use_hyde=req.use_hyde,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Index not ready: {e}") from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ChatResponse(
        answer=result.answer,
        sources=result.sources,
        latency_ms=result.latency_ms,
        trace=result.trace,
        from_cache=result.from_cache,
        fallback=result.fallback,
        attempts=result.attempts,
    )


def _sse_format(event_type: str, payload: dict) -> str:
    """Format one SSE message."""
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE endpoint. Browser EventSource doesn't speak POST natively, so the
    frontend uses fetch() + a ReadableStream reader. The events we emit:

      event: event   -> a HealingEvent dict (each loop step)
      event: token   -> a fragment of the answer text
      event: final   -> the full ChatResponse payload at the end
      event: error   -> something blew up; payload has {message}
    """
    record_request()  # reset idle timer — same as /chat, prevents VPS cron from killing us

    def gen():
        try:
            for event_type, payload in stream_self_healing(
                query=req.query,
                history=req.history,
                top_k=req.top_k,
                use_reranker=req.use_reranker,
                use_hyde=req.use_hyde,
            ):
                yield _sse_format(event_type, payload)
        except FileNotFoundError as e:
            yield _sse_format("error", {"message": f"Index not ready: {e}"})
        except Exception as e:
            yield _sse_format("error", {"message": str(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx/Cloudflare buffer SSE by default; this header tells them not to.
            "X-Accel-Buffering": "no",
        },
    )
