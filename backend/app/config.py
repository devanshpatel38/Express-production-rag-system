"""Application settings loaded from environment.

All knobs live here so we never sprinkle env reads across the codebase.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "express-docs-rag"
    environment: Literal["dev", "prod"] = "dev"
    cors_origins: str = "http://localhost:3000"

    # --- LLM ---
    # Provider switch keeps the generator swappable without code edits.
    llm_provider: Literal["openai", "gemini"] = "gemini"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    # --- Embeddings ---
    # Local sentence-transformers keeps inference free; swap to OpenAI for prod scale.
    embedding_backend: Literal["local", "openai"] = "local"
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    openai_embedding_model: str = "text-embedding-3-small"

    # --- Reranker ---
    # Cohere free tier covers dev; disable to skip reranking entirely.
    reranker_enabled: bool = True
    cohere_api_key: str | None = None
    cohere_rerank_model: str = "rerank-english-v3.0"

    # --- Retrieval ---
    chunk_size: int = 700  # chars; tuned for express docs which are short-paragraph heavy
    chunk_overlap: int = 120
    top_k_dense: int = 15
    top_k_bm25: int = 15
    top_k_rerank: int = 5     # what actually goes into the prompt
    hybrid_alpha: float = Field(default=0.5, ge=0.0, le=1.0)  # 0 = pure bm25, 1 = pure dense

    # --- Self-healing RAG ---
    # The "closed loop" upgrades. Each can be toggled independently so you can demo
    # the system with and without them and compare eval scores. All gated behind one
    # master flag so legacy /chat behavior is preserved when disabled.
    self_healing_enabled: bool = True
    # Step 1: route off-topic queries away from the heavy pipeline.
    adaptive_routing_enabled: bool = True
    # Step 2: rewrite the query as a hypothetical answer before embedding (HyDE).
    hyde_enabled: bool = False  # off by default - extra LLM call, opt-in via /chat
    # Step 3: LLM grades each retrieved chunk for relevance; low scores get filtered.
    retrieval_grading_enabled: bool = True
    grading_keep_threshold: float = 0.3        # score floor to keep a chunk (permissive; 0.55 filters comparison questions)
    grading_min_keep_ratio: float = 0.5        # below this we trigger query rewrite
    # Step 4: post-generation faithfulness check.
    faithfulness_check_enabled: bool = True
    faithfulness_threshold: float = 0.6
    # Step 5: bounded self-healing loop.
    max_healing_attempts: int = 2  # initial + 1 retry; larger blows up latency.

    # --- Semantic cache ---
    # Cheap in-memory cache to short-circuit repeated/similar queries. Per-process,
    # cleared on restart - swap to Redis if you need cross-instance persistence.
    semantic_cache_enabled: bool = True
    semantic_cache_threshold: float = 0.95  # cosine similarity to count as a hit
    semantic_cache_size: int = 256          # entries before we LRU-evict

    # --- Storage ---
    chroma_path: str = "./data/chroma"
    bm25_index_path: str = "./data/bm25.pkl"
    docs_meta_path: str = "./data/docs_meta.json"
    collection_name: str = "express_docs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
