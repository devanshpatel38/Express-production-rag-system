# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A production-shaped RAG chatbot grounded in the official Express.js documentation. Backend is a FastAPI Python app; frontend is Next.js 14. All backend commands must be run from the `backend/` directory (paths like `./data/` are relative to it).

## Commands

### Backend

```bash
cd backend

# Setup (first time)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Unix/Mac
pip install -r requirements.txt
cp .env.example .env            # then fill in API keys

# Build the search index (must be done before serving)
python -m scripts.ingest --source ../external/expressjs.com/en

# Serve
uvicorn app.main:app --reload --port 8000

# Eval
python -m eval.run_eval                    # full run, writes report to eval/reports/
python -m eval.run_eval --check-thresholds # CI mode, exits non-zero on regression
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local      # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev                     # http://localhost:3000
npm run build
npm run typecheck               # tsc --noEmit
npm run lint
```

## Architecture

### Request lifecycle

```
POST /chat
  └─ pipeline.run_pipeline(query, history)
       ├─ HybridRetriever.retrieve(query)
       │    ├─ dense:  embed(query) → Chroma top-15 (cosine similarity)
       │    ├─ sparse: tokenise → BM25 top-15
       │    └─ fuse:   min-max normalise both, weighted sum (HYBRID_ALPHA)
       ├─ Reranker.rerank(query, top-30, k=5)   ← Cohere or passthrough
       └─ Generator.generate(query, top-5, history)  ← Gemini or OpenAI
            └─ returns answer + source citations
```

### Key modules

| Path | Responsibility |
|---|---|
| `app/config.py` | Single source of truth for all settings via `get_settings()` (pydantic-settings + `.env`) |
| `app/rag/pipeline.py` | Thin glue: calls retriever → reranker → generator in sequence |
| `app/rag/retriever.py` | `HybridRetriever` — fuses Chroma dense search with BM25 sparse search |
| `app/rag/generator.py` | `Generator` protocol with `_OpenAIGenerator` / `_GeminiGenerator` implementations |
| `app/rag/reranker.py` | Cohere cross-encoder reranker (or passthrough when disabled) |
| `app/ingestion/chunker.py` | Markdown-aware sliding-window chunker that carries heading breadcrumbs into metadata |
| `app/ingestion/indexer.py` | Builds both Chroma vectors and BM25 pickle from chunks |
| `scripts/ingest.py` | CLI entry point that wires loader → chunker → indexer |
| `eval/run_eval.py` | Runs live pipeline against `eval/dataset.json`, scores with Ragas |
| `frontend/src/lib/api.ts` | Typed fetch wrapper — all backend calls go through here |

### Data on disk (backend/data/)

Three files must exist before the server can handle requests:
- `chroma/` — Chroma persistent vector store
- `bm25.pkl` — BM25 index pickle (`{bm25, ids}`)
- `docs_meta.json` — chunk_id → full chunk record (sidecar lookup used during fusion)

### Singleton pattern

`HybridRetriever`, `Generator`, and `Reranker` are all `@lru_cache` singletons loaded at first request. Changing settings requires a server restart.

### LLM provider switching

Set `LLM_PROVIDER=gemini` or `LLM_PROVIDER=openai` in `.env`. Same prompt template is used for both, so eval results are comparable across providers.

### Retrieval tuning knobs (all in `.env`)

- `HYBRID_ALPHA` — blend weight: `0.0` = pure BM25, `1.0` = pure dense, `0.5` default
- `TOP_K_DENSE` / `TOP_K_BM25` — candidates per retriever before fusion
- `TOP_K_RERANK` — how many chunks actually reach the LLM prompt
- `RERANKER_ENABLED` — set `false` to skip Cohere during heavy local runs

### Eval thresholds (CI)

Defined in `eval/run_eval.py::THRESHOLDS`. The CI workflow (`eval.yml`) runs `--check-thresholds` and fails the build if any Ragas metric drops below:

| Metric | Floor |
|---|---|
| faithfulness | 0.70 |
| answer_relevancy | 0.70 |
| context_precision | 0.55 |
| context_recall | 0.55 |

Ragas needs a scoring LLM: set `OPENAI_API_KEY`, or set `GEMINI_API_KEY` with `langchain-google-genai` installed (already in `requirements.txt`).
