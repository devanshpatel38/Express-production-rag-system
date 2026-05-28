# Backend

FastAPI service that runs the RAG pipeline and exposes `/chat` + `/health`.

## Layout

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, router wiring
│   ├── config.py            # Settings (env-backed, single source of truth)
│   ├── models/schemas.py    # Pydantic request/response models
│   ├── routers/
│   │   ├── chat.py          # POST /chat
│   │   └── health.py        # GET  /health
│   ├── rag/
│   │   ├── embeddings.py    # Local (MiniLM) and OpenAI embedders
│   │   ├── retriever.py     # Hybrid: Chroma + BM25 with min-max fusion
│   │   ├── reranker.py      # Cohere rerank wrapper (passthrough if no key)
│   │   ├── generator.py     # OpenAI / Gemini behind one Protocol
│   │   └── pipeline.py      # Orchestrates retrieve → rerank → generate
│   └── ingestion/
│       ├── loader.py        # Walks markdown corpus
│       ├── chunker.py       # Header-aware sliding-window chunker
│       └── indexer.py       # Persists Chroma + BM25 indices
├── eval/
│   ├── dataset.json         # Hand-curated Q&A eval set
│   └── run_eval.py          # Ragas runner, threshold gate
├── scripts/
│   └── ingest.py            # CLI entrypoint for the indexer
├── data/                    # Persisted indices live here after ingest
├── requirements.txt
├── Dockerfile
└── .env.example
```

## Local dev

See [`../docs/SETUP.md`](../docs/SETUP.md).

## API

### `GET /health`

Lightweight readiness probe. Returns indexed-chunk count and config.

### `POST /chat`

Request:

```json
{
  "query": "How do I serve static files?",
  "history": [],
  "top_k": 5,
  "use_reranker": true
}
```

`top_k` and `use_reranker` are optional overrides — useful for the eval
harness and the playground toggle in the UI.

Response:

```json
{
  "answer": "Use express.static('public') ...",
  "sources": [
    {
      "chunk_id": "...",
      "source_path": "en/starter/static-files.md",
      "title": "Serving static files in Express",
      "snippet": "To serve static files...",
      "score": 0.9421
    }
  ],
  "latency_ms": 842
}
```

## Tuning knobs

All in `.env` / `app/config.py`:

| Variable | Default | Effect |
| --- | --- | --- |
| `CHUNK_SIZE` | 700 | Characters per chunk |
| `CHUNK_OVERLAP` | 120 | Chars shared between adjacent chunks |
| `TOP_K_DENSE` | 15 | How many dense hits to pull |
| `TOP_K_BM25` | 15 | How many BM25 hits to pull |
| `TOP_K_RERANK` | 5 | Final count passed to the LLM |
| `HYBRID_ALPHA` | 0.5 | Dense weight (1 = pure dense, 0 = pure BM25) |
| `RERANKER_ENABLED` | true | Toggle the rerank stage |

Re-run the eval after any change.
