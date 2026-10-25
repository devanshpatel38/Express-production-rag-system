# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A RAG chatbot grounded in Apple's iMac Product Environmental Report (`iMac_PER_Oct2024.pdf`, 12 pages, in the repo root). Backend is a FastAPI Python 3.11 app; frontend is Next.js 14. The pipeline is a straight retrieve -> rerank -> generate. All backend commands must be run from the `backend/` directory (paths like `./data/` and `../iMac_PER_Oct2024.pdf` are relative to it).

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
python -m scripts.ingest        # --source defaults to settings.source_pdf_path (../iMac_PER_Oct2024.pdf)

# Serve
uvicorn app.main:app --reload --port 8000

# Tests
pytest

# Eval
python -m eval.run_eval                    # full run, writes report to eval/reports/
python -m eval.run_eval --check-thresholds # CI mode, exits non-zero on regression
```

`run_eval` also takes `--output PATH`, `--limit N`, `--sleep SECONDS`.

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
POST /chat  or  POST /chat/stream
  └─ pipeline.retrieve_and_rerank(query)
       ├─ HybridRetriever.retrieve(query)
       │    ├─ dense:  embed(query) -> Chroma top-15 (cosine similarity)
       │    ├─ sparse: tokenise -> BM25 top-15
       │    └─ fuse:   min-max normalise both, weighted sum (HYBRID_ALPHA)
       └─ Reranker.rerank(query, candidates, k)   <- Cohere or passthrough
  └─ Generator.generate / stream(query, top chunks, history)  <- Gemini or OpenAI
       └─ answer + sources (page, units, chunk type)
```

`/chat` returns one JSON response. `/chat/stream` is Server-Sent Events: `token` events, then one `final` event carrying the full response (`error` on failure). `GET /health` reports indexed chunk count, LLM provider and reranker status.

### Key modules

| Path | Responsibility |
|---|---|
| `app/config.py` | Single source of truth for all settings via `get_settings()` (pydantic-settings + `.env`) |
| `app/models/schemas.py` | Request/response models; `Source` carries `page`, `units`, `chunk_type` |
| `app/routers/chat.py`, `health.py` | `/chat`, `/chat/stream`, `/health` |
| `app/rag/pipeline.py` | Glue: `retrieve_and_rerank` then generate; builds sources |
| `app/rag/retriever.py` | `HybridRetriever` - fuses Chroma dense search with BM25 sparse search |
| `app/rag/embeddings.py` | Local sentence-transformers (MiniLM, 384-dim) or OpenAI embedder |
| `app/rag/reranker.py` | Cohere cross-encoder reranker (or passthrough when disabled / no key) |
| `app/rag/generator.py` | `Generator` protocol with `_OpenAIGenerator` / `_GeminiGenerator`, `generate` and `stream` |
| `app/ingestion/pdf_spans.py` | Span-aware PyMuPDF block extraction; drops superscript footnote markers (size ratio <= 0.8, numeric-only), keeps chemical subscripts |
| `app/ingestion/pdf_text.py` | `normalize_text` (mojibake, nbsp, de-hyphenation not across digits, whitespace) and running-header detection/removal |
| `app/ingestion/pdf_layout.py` | Column gutter detection and band-based reading order |
| `app/ingestion/pdf_tables.py` | Strict table validation; `find_tables` is only an anchor, rows rebuilt from word positions (the power-consumption table on page 12) |
| `app/ingestion/pdf_loader.py` | `load_pdf` -> `LoadedDoc` of per-page prose, tables and section (breadcrumb) |
| `app/ingestion/pdf_chunker.py` | `chunk_document`: sliding-window prose chunks + one key-value chunk per table row |
| `app/ingestion/indexer.py` | `build_indices`: Chroma vectors, BM25 pickle, `docs_meta.json` |
| `scripts/ingest.py` | CLI wiring loader -> chunker -> indexer |
| `eval/run_eval.py` | Runs live pipeline against `eval/dataset.json`, scores with Ragas, page-based hit-rate |
| `frontend/src/lib/api.ts` | Typed fetch wrapper - all backend calls go through here |

### Chunk metadata

Each chunk has: `chunk_id`, `source_path`, `title`, `section`, `text`, `page` (1-based), `chunk_type` (`prose` | `table_row`), `units`, `table_title`, `char_start`, `char_end`. The built index is 50 chunks over 12 pages.

### Data on disk (backend/data/)

Three files must exist before the server can handle requests:
- `chroma/` - Chroma persistent vector store (collection `imac_report`)
- `bm25.pkl` - BM25 index pickle (`{bm25, ids}`)
- `docs_meta.json` - chunk_id -> full chunk record (sidecar lookup used during fusion)

### Singleton pattern

`HybridRetriever`, `Generator`, and `Reranker` are `@lru_cache` singletons loaded at first request. Changing settings requires a server restart.

### LLM provider switching

Set `LLM_PROVIDER=gemini` or `LLM_PROVIDER=openai` in `.env`. The same prompt template is used for both, so eval results are comparable across providers.

### Retrieval tuning knobs (all in `.env`)

- `HYBRID_ALPHA` - blend weight: `0.0` = pure BM25, `1.0` = pure dense, `0.5` default
- `TOP_K_DENSE` / `TOP_K_BM25` - candidates per retriever before fusion (15 each)
- `TOP_K_RERANK` - how many chunks reach the LLM prompt (default 10)
- `CHUNK_SIZE` / `CHUNK_OVERLAP` - prose window, 700 / 120 characters
- `RERANKER_ENABLED` - set `false` to skip Cohere during heavy local runs
- `EMBEDDING_BACKEND` - `local` (default) or `openai`; re-ingest if changed

### Eval thresholds (CI)

Defined in `eval/run_eval.py::THRESHOLDS`. The CI workflow (`eval.yml`) runs `--check-thresholds` and fails the build if any Ragas metric drops below:

| Metric | Floor |
|---|---|
| faithfulness | 0.70 |
| answer_relevancy | 0.70 |
| context_precision | 0.55 |
| context_recall | 0.55 |

A page-based retrieval hit-rate is reported alongside. Latest scores: faithfulness 0.73, answer_relevancy 0.97, context_precision 0.87, context_recall 0.94, hit-rate 100%.

Ragas needs a scoring LLM: set `OPENAI_API_KEY`, or set `GEMINI_API_KEY` with `langchain-google-genai` installed (already in `requirements.txt`).
