"""POST /chat - the only public-facing RAG endpoint."""
from fastapi import APIRouter, HTTPException

from app.models.schemas import ChatRequest, ChatResponse
from app.rag.pipeline import run_pipeline
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

    return ChatResponse(answer=result.answer, sources=result.sources, latency_ms=result.latency_ms)