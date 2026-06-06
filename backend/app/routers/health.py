"""Lightweight readiness probe used by Render's health check and the frontend."""
from pathlib import Path

from fastapi import APIRouter

from app.config import get_settings
from app.models.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    s = get_settings()

    indexed = 0
    status = "ok"
    bm25 = Path(s.bm25_index_path)
    if bm25.exists():
        try:
            import pickle

            with bm25.open("rb") as f:
                payload = pickle.load(f)
            indexed = len(payload.get("ids", []))
        except Exception:
            status = "degraded"
    else:
        status = "degraded"

    return HealthResponse(
        status=status,
        indexed_chunks=indexed,
        llm_provider=s.llm_provider,
        reranker_enabled=s.reranker_enabled,
        self_healing_enabled=s.self_healing_enabled,
    )
