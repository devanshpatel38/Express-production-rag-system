"""Wire-format models. Keeping these isolated makes the contract obvious."""
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)
    # Letting the client override these is useful for the playground / eval runs.
    top_k: int | None = None
    use_reranker: bool | None = None


class Source(BaseModel):
    chunk_id: str
    source_path: str  # source document (PDF) filename
    title: str
    snippet: str
    score: float
    page: int = 0
    units: str = ""
    chunk_type: str = "prose"


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    latency_ms: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    indexed_chunks: int
    llm_provider: str
    reranker_enabled: bool
