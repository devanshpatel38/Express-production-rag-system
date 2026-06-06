# Backend

FastAPI service that runs the self-healing RAG pipeline and exposes
`/chat` (synchronous), `/chat/stream` (SSE), and `/health`.

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
│   │   ├── retriever.py     # Hybrid: Chroma + BM25 with min-max fusion (+ HyDE embed override)
│   │   ├── reranker.py      # Cohere rerank wrapper (passthrough if no key)
│   │   ├── router.py        # Adaptive query router: clear / ambiguous / off_topic
│   │   ├── grader.py        # LLM per-chunk relevance grading (CRAG)
│   │   ├── query_rewriter.py# HyDE + healing query rewrite
│   │   ├── verifier.py      # Post-generation faithfulness check
│   │   ├── cache.py         # In-memory semantic cache (cosine ≥ threshold)
│   │   ├── generator.py     # OpenAI / Gemini behind one Protocol (+ token streaming)
│   │   └── pipeline.py      # Self-healing loop + naive path + SSE generator
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

Lightweight readiness probe. Returns indexed-chunk count and config:

```json
{
  "status": "ok",
  "indexed_chunks": 345,
  "llm_provider": "openai",
  "reranker_enabled": true,
  "self_healing_enabled": true
}
```

### `POST /chat`

Synchronous. Runs the full pipeline and returns the complete answer in one JSON.

Request:

```json
{
  "query": "How do I serve static files?",
  "history": [],
  "top_k": 5,
  "use_reranker": true,
  "use_self_healing": true,
  "use_hyde": false
}
```

All fields except `query` are optional overrides — useful for the eval harness
and the playground toggles in the UI. When an override is omitted the server
default (from `.env`) is used. `use_self_healing: false` runs the legacy
`retrieve → rerank → generate` path.

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
  "latency_ms": 842,
  "trace": [
    { "stage": "routing",      "attempt": 1, "message": "Routed as 'clear'" },
    { "stage": "retrieval",    "attempt": 1, "message": "Hybrid retrieval returned 27 candidates" },
    { "stage": "grading",      "attempt": 1, "message": "Grader kept 5/5 chunks (avg 0.76)", "score": 0.76 },
    { "stage": "faithfulness", "attempt": 1, "message": "Faithfulness 1.00", "score": 1.0 },
    { "stage": "done",         "attempt": 1, "message": "Answer accepted" }
  ],
  "from_cache": false,
  "fallback": false,
  "attempts": 1
}
```

- `trace` — ordered `HealingEvent`s; empty when self-healing is off.
- `from_cache` — answer served from the semantic cache.
- `fallback` — the answer failed the faithfulness gate and a graceful fallback was returned.
- `attempts` — how many self-healing iterations the request consumed (1 = first try worked).

### `POST /chat/stream`

Same request schema, delivered as **Server-Sent Events**. Always runs the
self-healing path. Event types:

| `event:` | `data:` payload | When |
| --- | --- | --- |
| `event` | a `HealingEvent` dict | each pipeline step finishes |
| `token` | `{ "text": "..." }` | a fragment of the answer |
| `final` | full `ChatResponse` (answer, sources, trace, …) | after the stream completes |
| `error` | `{ "message": "..." }` | something failed mid-stream |

`EventSource` only supports GET, so clients `POST` and parse the stream by hand
(see `frontend/src/lib/api.ts → chatStream`).

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

### Self-healing

| Variable | Default | Effect |
| --- | --- | --- |
| `SELF_HEALING_ENABLED` | true | Master switch; off = legacy retrieve → rerank → generate |
| `ADAPTIVE_ROUTING_ENABLED` | true | Short-circuit off-topic queries before retrieval |
| `HYDE_ENABLED` | false | Embed a hypothetical answer before dense retrieval (extra LLM call; also opt-in per request) |
| `RETRIEVAL_GRADING_ENABLED` | true | LLM grades each chunk; weak ones are filtered |
| `GRADING_KEEP_THRESHOLD` | 0.3 | Min relevance score to keep a chunk |
| `GRADING_MIN_KEEP_RATIO` | 0.5 | Below this kept-ratio, trigger a query rewrite |
| `FAITHFULNESS_CHECK_ENABLED` | true | Post-generation grounding check |
| `FAITHFULNESS_THRESHOLD` | 0.6 | Below this score, rewrite and retry |
| `MAX_HEALING_ATTEMPTS` | 2 | Retry budget (initial + retries); higher = more latency |

### Semantic cache

| Variable | Default | Effect |
| --- | --- | --- |
| `SEMANTIC_CACHE_ENABLED` | true | Short-circuit repeated/paraphrased queries |
| `SEMANTIC_CACHE_THRESHOLD` | 0.95 | Cosine similarity to count as a cache hit |
| `SEMANTIC_CACHE_SIZE` | 256 | Entries before LRU eviction |

Re-run the eval after any change.
