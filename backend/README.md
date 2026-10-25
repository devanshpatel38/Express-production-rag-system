# Backend

FastAPI service for the iMac Product Environmental Report chatbot. It runs a
**retrieve, rerank, generate** pipeline and exposes `/health`, `/chat` and `/chat/stream`.
Run every command from this `backend/` directory.

## Layout

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, router wiring
│   ├── config.py            # Settings (env-backed, single source of truth)
│   ├── models/schemas.py    # Request/response models
│   ├── routers/
│   │   ├── chat.py          # POST /chat and POST /chat/stream (SSE)
│   │   └── health.py        # GET /health
│   ├── rag/
│   │   ├── embeddings.py    # Local (MiniLM) and OpenAI embedders
│   │   ├── retriever.py     # Hybrid: Chroma dense + BM25, min-max fusion
│   │   ├── reranker.py      # Cohere rerank (passthrough without a key)
│   │   ├── generator.py     # Gemini / OpenAI behind one interface, with streaming
│   │   └── pipeline.py      # retrieve -> rerank -> generate
│   └── ingestion/
│       ├── pdf_spans.py     # Span-aware block extraction, strips footnote markers
│       ├── pdf_text.py      # Text normalization and running-header removal
│       ├── pdf_layout.py    # Column gutter detection and reading order
│       ├── pdf_tables.py    # Strict table detection, one record per row
│       ├── pdf_loader.py    # Combines the above into per-page prose + tables
│       ├── pdf_chunker.py   # Sliding-window prose chunks + table-row chunks
│       └── indexer.py       # Writes Chroma, BM25 pickle and docs_meta.json
├── eval/
│   ├── dataset.json         # Hand-verified question set
│   └── run_eval.py          # Ragas runner and threshold gate
├── scripts/ingest.py        # CLI: loader -> chunker -> indexer
├── tests/
├── data/                    # Built indexes live here
├── requirements.txt
├── Dockerfile
└── .env.example
```

## The pipeline

1. **Hybrid retrieval.** The query is embedded and searched in ChromaDB (dense), and
   tokenised and searched with BM25 (sparse). Each score list is min-max normalised and
   blended: `alpha * dense + (1 - alpha) * bm25`.
2. **Reranking.** A Cohere cross-encoder re-orders the fused candidates and keeps the top
   `TOP_K_RERANK`. With no Cohere key, or `RERANKER_ENABLED=false`, the fused order is used.
3. **Generation.** Gemini or OpenAI answers from the kept chunks only, citing the page and
   the units of each figure. The same prompt is used for both providers.

## Ingestion

`python -m scripts.ingest` reads the PDF with PyMuPDF and builds the index (50 chunks over
12 pages):

- `pdf_spans` reads text span by span and drops tiny superscript footnote markers, but keeps
  chemical subscripts and real figures ("391 kg CO2e").
- `pdf_text` repairs garbled characters, converts non-breaking spaces, rejoins words split by
  a line-end hyphen (never across digits), and collapses stray whitespace. It also detects
  and removes the repeating "iMac | Product Environmental Report N" header.
- `pdf_layout` finds the column gutter from the blocks' own positions and splits the page
  into bands so multi-column pages read in the right order.
- `pdf_tables` accepts only genuine grids (the power-consumption table: modes by
  100V / 115V / 230V) and rebuilds each row with its units.
- `pdf_loader` combines these into per-page prose and tables; the running section becomes the
  page's breadcrumb.
- `pdf_chunker` makes sliding-window prose chunks (`CHUNK_SIZE` / `CHUNK_OVERLAP`) and one
  key-value chunk per table row.
- `indexer` writes the Chroma collection, the BM25 pickle and `docs_meta.json`.

Every chunk carries: page (1-based), section, chunk type (`prose` or `table_row`), units,
table title and source file.

## Commands

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Unix: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env              # fill in keys

python -m scripts.ingest          # --source defaults to ../iMac_PER_Oct2024.pdf
uvicorn app.main:app --reload --port 8000

pytest                            # unit tests
python -m eval.run_eval           # full eval, writes eval/reports/
python -m eval.run_eval --check-thresholds
```

`run_eval` also accepts `--output PATH`, `--limit N` and `--sleep SECONDS`.

## API

### `GET /health`

```json
{ "status": "ok", "indexed_chunks": 50, "llm_provider": "gemini", "reranker_enabled": true }
```

`status` is `degraded` when the BM25 index is missing or unreadable.

### `POST /chat`

Request (only `query` is required):

```json
{ "query": "How much electricity does the iMac use in sleep mode?", "history": [], "top_k": 5, "use_reranker": true }
```

Response:

```json
{
  "answer": "...",
  "sources": [
    {
      "chunk_id": "...",
      "source_path": "iMac_PER_Oct2024.pdf",
      "title": "...",
      "snippet": "...",
      "score": 0.94,
      "page": 12,
      "units": "W",
      "chunk_type": "table_row"
    }
  ],
  "latency_ms": 842
}
```

### `POST /chat/stream`

Same request, delivered as Server-Sent Events:

| `event:` | `data:` | When |
| --- | --- | --- |
| `token` | `{ "text": "..." }` | each fragment of the answer |
| `final` | full chat response (answer, sources, latency) | once, at the end |
| `error` | `{ "message": "..." }` | something failed |

Browsers' `EventSource` only supports GET, so the frontend POSTs and parses the stream
itself (`frontend/src/lib/api.ts`).

## Configuration

All settings live in `.env` and are read in `app/config.py`.

| Variable | Default | Effect |
| --- | --- | --- |
| `LLM_PROVIDER` | gemini | `gemini` or `openai` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | empty | Key for the chosen provider |
| `EMBEDDING_BACKEND` | local | `local` (MiniLM) or `openai` |
| `RERANKER_ENABLED` | true | Turn the Cohere rerank step on or off |
| `COHERE_API_KEY` | empty | Needed for reranking |
| `SOURCE_PDF_PATH` | ../iMac_PER_Oct2024.pdf | PDF the ingest script reads |
| `CHUNK_SIZE` | 700 | Characters per prose chunk |
| `CHUNK_OVERLAP` | 120 | Characters shared by neighbouring chunks |
| `TOP_K_DENSE` | 15 | Dense candidates before fusion |
| `TOP_K_BM25` | 15 | BM25 candidates before fusion |
| `TOP_K_RERANK` | 10 | Chunks passed to the LLM |
| `HYBRID_ALPHA` | 0.5 | 0 = pure BM25, 1 = pure dense |
| `CORS_ORIGINS` | http://localhost:3000 | Allowed browser origins |

Retriever, reranker and generator are loaded once at the first request, so restart the
server after changing settings. Re-run the eval after tuning.

## Eval

The Ragas harness scores faithfulness, answer relevancy, context precision and context
recall over `eval/dataset.json`, plus a page-based retrieval hit-rate. Floors: 0.70, 0.70,
0.55, 0.55. See [`../docs/EVAL.md`](../docs/EVAL.md).
