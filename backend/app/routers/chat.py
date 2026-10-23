"""Chat endpoints.

  POST /chat         : synchronous, returns full ChatResponse JSON.
                       Used by the eval harness and by clients that don't want SSE.
  POST /chat/stream  : Server-Sent Events. Streams the answer token-by-token,
                       then a final payload with sources.

Both share the same request schema.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest, ChatResponse
from app.rag.pipeline import run_pipeline, stream_pipeline
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
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Index not ready: {e}") from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ChatResponse(
        answer=result.answer,
        sources=result.sources,
        latency_ms=result.latency_ms,
    )


def _sse_format(event_type: str, payload: dict) -> str:
    """Format one SSE message."""
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE endpoint. Browser EventSource doesn't speak POST natively, so the
    frontend uses fetch() + a ReadableStream reader. The events we emit:

      event: token   -> a fragment of the answer text
      event: final   -> the full ChatResponse payload at the end
      event: error   -> something blew up; payload has {message}
    """
    record_request()  # reset idle timer — same as /chat, prevents VPS cron from killing us

    def gen():
        try:
            for event_type, payload in stream_pipeline(
                query=req.query,
                history=req.history,
                top_k=req.top_k,
                use_reranker=req.use_reranker,
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
