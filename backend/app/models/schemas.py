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
    # Self-healing master switch. None means "use server default from config".
    use_self_healing: bool | None = None
    # HyDE is an extra LLM call so we keep it opt-in even when self-healing is on.
    use_hyde: bool | None = None


class Source(BaseModel):
    chunk_id: str
    source_path: str  # original markdown file path
    title: str
    snippet: str
    score: float


# --- Self-healing telemetry ---
# Every stage of the loop appends an event. The UI shows these as a timeline so
# the user can see *why* an answer changed (or why it took longer). Keeping the
# shape lightweight - strings + numbers - so it serialises cleanly over SSE too.

EventStage = Literal[
    "routing",          # adaptive router decision
    "cache_hit",        # semantic cache short-circuit
    "hyde",             # hypothetical document embedding
    "retrieval",        # hybrid retrieval finished
    "grading",          # per-chunk relevance grading
    "rerank",           # cross-encoder rerank
    "rewrite",          # query rewriter fired
    "generation",       # LLM produced an answer
    "faithfulness",     # post-generation grounding check
    "retry",            # loop is restarting
    "give_up",          # max attempts hit, returning best effort
    "done",             # final answer accepted
]


class HealingEvent(BaseModel):
    stage: EventStage
    attempt: int = 1            # which loop iteration this event belongs to
    message: str                 # human-readable, shown in the UI
    score: float | None = None   # optional numeric (e.g. faithfulness=0.78)
    detail: dict | None = None   # optional structured payload (rewritten query, etc.)


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    latency_ms: int
    # The healing trace. Empty list when self-healing is disabled.
    trace: list[HealingEvent] = Field(default_factory=list)
    # True when we returned a previously-computed answer from the semantic cache.
    from_cache: bool = False
    # True when the final answer failed the faithfulness check and we returned a
    # graceful fallback. UI can warn the user.
    fallback: bool = False
    # How many self-healing attempts the request consumed (1 = first try worked).
    attempts: int = 1


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    indexed_chunks: int
    llm_provider: str
    reranker_enabled: bool
    self_healing_enabled: bool
