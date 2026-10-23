# Backend

FastAPI service for the GPO Annual Report RAG chatbot. It builds a search index from
the U.S. Government Publishing Office (GPO) 2018 Annual Report PDF, then answers
questions from that index over REST (`/chat`), SSE (`/chat/stream`), and a readiness
probe (`/health`).

**Built by:** [Devansh Patel](https://portfolio-website-umber-ten-90.vercel.app/#)

## Request lifecycle

```
POST /chat  (or /chat/stream)
  └─ pipeline.run_pipeline(query, history)
       ├─ HybridRetriever.retrieve(query)
       │    ├─ dense:  embed(query) → Chroma top-k (cosine similarity)
       │    ├─ sparse: tokenise → BM25 top-k
       │    └─ fuse:   min-max normalise both, weighted sum (HYBRID_ALPHA)
       ├─ Reranker.rerank(query, candidates, k)   ← Cohere cross-encoder
       └─ Generator.generate(query, top-k chunks, history)  ← Gemini or OpenAI
            └─ returns a grounded answer + source citations
```

The generator answers using only the chunks that reach the prompt, states the units and
page for every number, and cites inline.

## Layout

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, router wiring
│   ├── config.py            # Settings (env-backed, single source of truth)
│   ├── models/schemas.py    # Pydantic request/response models
│   ├── routers/
│   │   ├── chat.py          # POST /chat (sync) + POST /chat/stream (SSE)
│   │   └── health.py        # GET  /health
│   ├── rag/
│   │   ├── embeddings.py    # Local (MiniLM) and OpenAI embedders
│   │   ├── retriever.py     # Hybrid: Chroma + BM25 with min-max fusion
│   │   ├── reranker.py      # Cohere cross-encoder rerank
│   │   ├── generator.py     # Gemini / OpenAI behind one interface
│   │   ├── pipeline.py      # retrieve → rerank → generate (+ streaming wrapper)
│   │   └── idle_manager.py  # Frees cached models after a quiet period
│   └── ingestion/
│       ├── pdf_loader.py    # PyMuPDF two-pass loader: per-page prose + validated tables
│       ├── pdf_text.py      # Text cleanup, running header/footer removal, section detection
│       ├── pdf_layout.py    # Column-aware reading-order resolution
│       ├── pdf_tables.py    # Table validation, packed-row splitting, per-row records
│       ├── pdf_chunker.py   # Prose windows + one chunk per table row
│       ├── chunker.py       # Chunk model and overlapping window splitter
│       └── indexer.py       # Persists Chroma vectors, BM25 index, and chunk metadata
├── scripts/
│   └── ingest.py            # CLI: PDF → chunks → indices
├── eval/
│   ├── dataset.json         # Verified gold Q&A set
│   ├── run_eval.py          # Ragas scoring + page-based hit-rate + threshold gate
│   └── reports/             # Eval reports
├── data/                    # Index files written by ingest
├── requirements.txt
├── Dockerfile
└── .env.example
```

## Ingestion

`scripts/ingest.py` wires the loader, chunker, and indexer together:

1. **Load and clean.** PyMuPDF reads each page. The text is cleaned: garbled characters
   are repaired, words hyphenated across line breaks are rejoined, letter-spaced headings
   (`G O V E R N M E N T` becomes `GOVERNMENT`) and odd whitespace are collapsed.
2. **Reading order.** Multi-column pages are reassembled left column then right, with
   full-width titles kept in place.
3. **Headers and footers.** Lines that repeat across many pages
   (`HEADER_FOOTER_MIN_RECURRENCE`) are stripped, and each page keeps its section as
   context.
4. **Tables.** Tables are detected and validated (page layouts such as org charts are
   rejected), stacked or newline-packed cells are split back into individual rows, and
   each row becomes a self-contained key-value record carrying the table's descriptor,
   units, and page.
5. **Prose.** Narrative text is split into overlapping windows (`CHUNK_SIZE`,
   `CHUNK_OVERLAP`) that keep their section and page.
6. **Index.** Every chunk is embedded into the ChromaDB collection `gpo_report` and added
   to a BM25 index, tagged with page, units, and chunk type.

```bash
python -m scripts.ingest --source ../GPO-Anual-report.pdf
python -m scripts.ingest --source ../GPO-Anual-report.pdf --max-pages 20   # quick test run
```

Each run rebuilds the index from scratch.

### Data on disk (`backend/data/`)

- `chroma/` — Chroma persistent vector store
- `bm25.pkl` — BM25 index pickle (`{bm25, ids}`)
- `docs_meta.json` — chunk id → full chunk record (text, page, units, section, type),
  used to look up chunks after fusion

## Run locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Unix/Mac
pip install -r requirements.txt
cp .env.example .env            # fill in API keys

python -m scripts.ingest --source ../GPO-Anual-report.pdf
uvicorn app.main:app --reload --port 8000
```

See [`../docs/SETUP.md`](../docs/SETUP.md) for the full walkthrough.

## API

### `GET /health`

Readiness probe. Returns the indexed-chunk count and active providers:

```json
{
  "status": "ok",
  "indexed_chunks": 1200,
  "llm_provider": "gemini",
  "reranker_enabled": true
}
```

`status` is `degraded` when the BM25 index file is not found or cannot be read.

### `POST /chat`

Runs the pipeline and returns the complete answer as JSON.

Request:

```json
{
  "query": "What were GPO's billings to the Department of State in 2018?",
  "history": [],
  "top_k": 5,
  "use_reranker": true
}
```

Only `query` is required. `history` carries earlier turns, and `top_k` and
`use_reranker` override the server defaults from `.env` for a single request.

Response:

```json
{
  "answer": "…",
  "sources": [
    {
      "chunk_id": "...",
      "source_path": "GPO-Anual-report.pdf",
      "title": "…",
      "snippet": "…",
      "score": 0.9421,
      "page": 42,
      "units": "Dollars in thousands",
      "chunk_type": "table_row"
    }
  ],
  "latency_ms": 842
}
```

### `POST /chat/stream`

Same request body, delivered as Server-Sent Events:

| `event:` | `data:` payload | When |
| --- | --- | --- |
| `token` | `{ "text": "..." }` | a fragment of the answer |
| `final` | `{ answer, sources, latency_ms }` | after the answer is complete |
| `error` | `{ "message": "..." }` | something failed |

`EventSource` only supports GET, so clients `POST` and parse the stream by hand
(see `frontend/src/lib/api.ts → chatStream`).

## Settings

All settings live in `app/config.py` and are read from `.env`.

| Variable | Default | Effect |
| --- | --- | --- |
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | — / `gemini-1.5-flash` | Gemini credentials and model |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — / `gpt-4o-mini` | OpenAI credentials and model |
| `EMBEDDING_BACKEND` | `local` | `local` (sentence-transformers) or `openai` |
| `LOCAL_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local embedding model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `RERANKER_ENABLED` | `true` | Turn the rerank stage on or off |
| `COHERE_API_KEY` / `COHERE_RERANK_MODEL` | — / `rerank-english-v3.0` | Cohere credentials and model |
| `CHUNK_SIZE` | 700 | Characters per prose chunk |
| `CHUNK_OVERLAP` | 120 | Characters shared between adjacent prose chunks |
| `TOP_K_DENSE` | 15 | Dense hits pulled before fusion |
| `TOP_K_BM25` | 15 | BM25 hits pulled before fusion |
| `TOP_K_RERANK` | 10 | Chunks that reach the LLM prompt |
| `HYBRID_ALPHA` | 0.5 | Dense weight: `1.0` = pure dense, `0.0` = pure BM25 |
| `SOURCE_PDF_PATH` | `../GPO-Anual-report.pdf` | Source PDF |
| `HEADER_FOOTER_MIN_RECURRENCE` | 8 | Pages a line must repeat on to count as a running header/footer |
| `CHROMA_PATH` | `./data/chroma` | Chroma store location |
| `BM25_INDEX_PATH` | `./data/bm25.pkl` | BM25 pickle location |
| `DOCS_META_PATH` | `./data/docs_meta.json` | Chunk record sidecar location |
| `COLLECTION_NAME` | `gpo_report` | Chroma collection name |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed browser origins |

The retriever, reranker, generator, and embedder are cached singletons loaded on the
first request, so changing a setting takes effect after a server restart.

## Eval

```bash
python -m eval.run_eval                    # full run, writes a report to eval/reports/
python -m eval.run_eval --check-thresholds # CI mode, exits non-zero on regression
```

The runner sends each question in `eval/dataset.json` through the live pipeline and
scores it with Ragas, plus a page-based retrieval hit-rate (does the retrieved set
include a reference page). CI (`eval.yml`) fails the build if any Ragas metric drops
below its floor:

| Metric | Floor |
| --- | --- |
| faithfulness | 0.70 |
| answer_relevancy | 0.70 |
| context_precision | 0.55 |
| context_recall | 0.55 |

Ragas needs a scoring LLM: set `OPENAI_API_KEY`, or set `GEMINI_API_KEY` with
`langchain-google-genai` installed (already in `requirements.txt`). Re-run the eval after
any change to retrieval or generation settings.

## License

MIT
