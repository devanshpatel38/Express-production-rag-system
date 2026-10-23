# Backend

**Built by:** [Devansh Patel](https://portfolio-website-umber-ten-90.vercel.app/#)

FastAPI service for the Global Economic Prospects RAG chatbot. It answers questions
from the World Bank report, quoting exact figures with their units and page. It exposes
`/chat` (synchronous), `/chat/stream` (SSE), and `/health`.

## Request lifecycle

```
POST /chat  or  POST /chat/stream
  └─ retrieve_and_rerank(query)
       ├─ HybridRetriever.retrieve(query)
       │    ├─ dense:  embed(query) → Chroma top-K (cosine similarity)
       │    ├─ sparse: tokenise → BM25 top-K
       │    └─ fuse:   min-max normalise both, weighted sum (HYBRID_ALPHA)
       └─ Reranker.rerank(query, candidates, top_k)   ← Cohere cross-encoder
  └─ Generator.generate(query, kept_chunks, history)  ← Gemini or OpenAI
       └─ answer using only those chunks, with units + page and inline citations
```

- `/chat` returns `{answer, sources, latency_ms}`.
- `/chat/stream` sends `token` events as the answer is written, then one `final` event
  with `{answer, sources, latency_ms}`. If something goes wrong it sends an `error`
  event.
- Each source carries its chunk id, title, a short snippet, the score, the **page**, the
  **units**, and the chunk type (`prose`, `table_row`, or `figure`).

## Layout

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, router wiring
│   ├── config.py            # Settings (env-backed, single source of truth)
│   ├── models/schemas.py    # Pydantic request/response models
│   ├── routers/
│   │   ├── chat.py          # POST /chat + POST /chat/stream (SSE)
│   │   └── health.py        # GET  /health
│   ├── rag/
│   │   ├── embeddings.py    # Local (MiniLM) and OpenAI embedders
│   │   ├── retriever.py     # Hybrid: Chroma dense + BM25 with min-max fusion
│   │   ├── reranker.py      # Cohere cross-encoder rerank
│   │   ├── generator.py     # Gemini / OpenAI behind one interface, with token streaming
│   │   ├── vision.py        # Describes figures using only the values printed on them
│   │   ├── pipeline.py      # retrieve → rerank → generate
│   │   └── idle_manager.py  # Releases loaded models after a period with no requests
│   └── ingestion/
│       ├── pdf_loader.py    # Reads the PDF page by page and assembles each page's content
│       ├── pdf_text.py      # Text cleanup and running header/footer removal
│       ├── pdf_layout.py    # Reading-order reassembly for multi-column pages
│       ├── pdf_tables.py    # Table detection, validation, and per-row records
│       ├── pdf_figures.py   # Figure detection and description
│       ├── pdf_chunker.py   # Prose windows, table-row chunks, figure chunks
│       ├── chunker.py       # The shared Chunk record
│       └── indexer.py       # Builds the Chroma index, BM25 index, and metadata file
├── scripts/ingest.py        # CLI: PDF → chunks → indexes
├── eval/
│   ├── dataset.json         # Verified gold Q&A set
│   ├── run_eval.py          # Ragas scoring + page-based retrieval hit-rate
│   └── reports/             # Written reports
└── tests/                   # pytest suite
```

## Ingestion

`scripts/ingest.py` turns the PDF into the search index:

1. **Read and clean.** PyMuPDF extracts each page. The text is cleaned: garbled
   characters are repaired, words split across line breaks are rejoined, and
   letter-spaced headers and odd whitespace are collapsed.
2. **Reading order.** Two-column pages are reassembled left column then right, with
   full-width titles kept in place.
3. **Headers and footers.** Lines that repeat across many pages are stripped, while the
   section each page belongs to is kept as context.
4. **Tables.** Tables are detected and validated (page layouts such as org charts are
   rejected). Each row becomes a self-contained key-value record carrying the table's
   title, units, and page.
5. **Figures.** Each figure is described using the values printed on it.
6. **Prose.** Narrative text is split into overlapping windows (`CHUNK_SIZE`,
   `CHUNK_OVERLAP`) that keep section and page.

Prose, table rows, and figures are all embedded into Chroma and indexed in BM25, each
tagged with page and units.

## Data on disk (`backend/data/`)

Three files must exist before the server can handle requests:

- `chroma/` — Chroma persistent vector store
- `bm25.pkl` — BM25 index pickle (`{bm25, ids}`)
- `docs_meta.json` — chunk id → full chunk record (text, section, page, units, chunk
  type), used to turn fused ids back into chunks

## Configuration

All settings live in `app/config.py` and are read from `.env`
(see `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `dev` | `dev` or `prod` |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed browser origins |
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | — / `gemini-1.5-flash` | Gemini settings |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — / `gpt-4o-mini` | OpenAI settings |
| `EMBEDDING_BACKEND` | `local` | `local` (sentence-transformers) or `openai` |
| `LOCAL_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local embedding model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `RERANKER_ENABLED` | `true` | Turn the Cohere rerank step on or off |
| `COHERE_API_KEY` / `COHERE_RERANK_MODEL` | — / `rerank-english-v3.0` | Cohere settings |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `700` / `120` | Prose window size and overlap (characters) |
| `TOP_K_DENSE` / `TOP_K_BM25` | `15` / `15` | Candidates per retriever before fusion |
| `TOP_K_RERANK` | `5` | Chunks that reach the LLM prompt |
| `HYBRID_ALPHA` | `0.5` | `0.0` = pure BM25, `1.0` = pure dense |
| `SOURCE_PDF_PATH` | `../GEP-Jun-2026.pdf` | The report PDF |
| `VISION_ENABLED` | `true` | Describe figures during ingestion |
| `HEADER_FOOTER_MIN_RECURRENCE` | `10` | Lines repeated on at least this many pages are stripped |
| `CHROMA_PATH` / `BM25_INDEX_PATH` / `DOCS_META_PATH` | `./data/...` | Index locations |
| `COLLECTION_NAME` | `gep_report` | Chroma collection name |
| `IDLE_TIMEOUT_SECONDS` | `60` | Seconds without a request before models are released |

The retriever, reranker, embedder, and generator are cached singletons loaded on the
first request, so changing settings needs a server restart.

## Run it

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Unix/Mac
pip install -r requirements.txt
cp .env.example .env            # fill in API keys

# Build the index from the report PDF
python -m scripts.ingest --source ../GEP-Jun-2026.pdf

# Serve
uvicorn app.main:app --reload --port 8000
```

`scripts/ingest.py` also accepts `--max-pages N` to process only the first N pages.

## Eval

```bash
python -m eval.run_eval                     # full run, writes a report to eval/reports/
python -m eval.run_eval --check-thresholds  # CI mode, exits non-zero on regression
```

The eval runs the live pipeline over the gold Q&A set and scores it with Ragas, plus a
page-based retrieval hit-rate (did the retrieved chunks include a reference page).
Thresholds are defined in `eval/run_eval.py` and checked by GitHub Actions:

| Metric | Floor |
|---|---|
| faithfulness | 0.70 |
| answer_relevancy | 0.70 |
| context_precision | 0.55 |
| context_recall | 0.55 |

Ragas needs a scoring LLM: set `OPENAI_API_KEY`, or set `GEMINI_API_KEY` with
`langchain-google-genai` installed.

## Tests

```bash
pytest
```

## License

MIT
