# Express Docs RAG

**Built by:** [Devansh Patel](https://portfolio-website-umber-ten-90.vercel.app/#)

A retrieval-augmented chatbot grounded in the official Express.js documentation.
Built to demonstrate a production-shaped, **self-healing** RAG pipeline end-to-end,
not a notebook demo — the system inspects its own retrieval and answers, corrects
itself when they're weak, and streams every step it takes to the UI.


## What's inside

- **Self-healing (Corrective) RAG loop** — instead of a blind `retrieve → generate`, the pipeline grades what it retrieves, rewrites the query and retries when retrieval is weak, verifies the answer is grounded, and falls back gracefully when it can't be confident. All stages are independently toggleable and bounded by a retry budget.
- **Adaptive routing** — off-topic questions are classified and short-circuited before they ever hit retrieval, so they don't burn the retrieval/LLM budget.
- **LLM chunk grading (CRAG)** — every retrieved chunk is scored for relevance; low-scoring "looks-related-but-useless" chunks are dropped before generation.
- **Query rewriting + HyDE** — vague or failed queries are rephrased toward documentation vocabulary; optional Hypothetical Document Embeddings embed an imagined answer for better dense recall.
- **Faithfulness check** — a post-generation pass scores how well the answer is supported by the retrieved context; low scores trigger a rewrite-and-retry.
- **SSE streaming** — the healing trace and the answer stream live to the browser over Server-Sent Events; the UI shows each pipeline step as it happens.
- **Semantic cache** — paraphrase-aware in-memory cache (cosine ≥ 0.95) short-circuits repeated/similar questions.
- **Hybrid retrieval** — dense embeddings (Chroma) fused with BM25, single `alpha` knob to control the blend.
- **Cross-encoder reranking** — Cohere Rerank narrows the top-k that actually reaches the LLM.
- **Eval harness** — Ragas (faithfulness, answer relevancy, context precision/recall) over a hand-curated Q&A set.
- **GitHub Actions** — eval runs on every PR and fails the build if scores drop below configured thresholds.
- **Multi-provider LLM** — Gemini and OpenAI behind one interface; provider chosen by env var.
- **Sourced answers + transparent trace** — every response carries inline citations, an expandable sources panel, and a collapsible self-healing trace showing exactly how the answer was reached.

Self-healing is a master switch (`SELF_HEALING_ENABLED`); turn it off and the
pipeline falls back to the classic `retrieve → rerank → generate` path, which the
eval harness uses to A/B the two modes.

## Architecture at a glance

```
  query
    │
    ▼
 ┌──────────────┐  off-topic ─▶ polite redirect (no retrieval, no LLM bill)
 │ 1. Router    │  ambiguous ─▶ force HyDE on
 └──────┬───────┘
        ▼
 ┌──────────────┐  cache hit (cosine ≥ 0.95) ─▶ return cached answer
 │ 2. Cache     │
 └──────┬───────┘
        ▼   ┌───── self-healing loop · bounded by MAX_HEALING_ATTEMPTS ──────┐
            │ 3. HyDE (optional)  embed a hypothetical answer                 │
            │ 4. Hybrid retrieve  dense (Chroma+MiniLM) + BM25, min-max fused │
            │ 5. Rerank           Cohere rerank-english-v3.0 → top-k          │
            │ 6. Grade            LLM scores each chunk; weak ones dropped     │
            │      └─ too few kept ──▶ rewrite query, retry ↺                 │
            │ 7. Generate         Gemini / OpenAI, from surviving chunks      │
            │ 8. Verify           faithfulness score                          │
            │      └─ below threshold ──▶ rewrite query, retry ↺             │
            └─────────────────────────────────────────────────────────────────┘
                       │ answer + sources + healing trace   (cached for next time)
                       ▼
            streamed to the UI over SSE, step by step
```

Every stage appends a `HealingEvent`; the `/chat/stream` endpoint emits those
events live, then streams the answer, then a final payload with sources and the
full trace. More detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | FastAPI (Python 3.11) | Async, typed, clean OpenAPI |
| Vector store | ChromaDB (persistent) | Embedded, no extra service |
| Sparse retrieval | rank_bm25 | Pure-Python, no Lucene/ES |
| Embeddings | sentence-transformers (default), OpenAI (optional) | Free dev, scalable swap |
| Reranker | Cohere Rerank v3 | Best quality/effort ratio |
| LLM | Gemini 1.5 Flash (default), GPT-4o-mini | Cheap, fast, swappable |
| Self-healing | Router + grader + rewriter + verifier (same LLM) | Corrective RAG without extra infra |
| Cache | In-memory semantic cache | Paraphrase-aware, zero external deps |
| Transport | REST `/chat` + SSE `/chat/stream` | Live healing trace + token streaming |
| Eval | Ragas + custom retrieval hit-rate | Standard metrics + sanity |
| Frontend | Next.js 14 (App Router) | Landing + chat, type-safe, SSE client |
| CI | GitHub Actions | Eval on PR, typecheck, build |

## Quickstart

See [`docs/SETUP.md`](docs/SETUP.md) for a step-by-step. The short version:

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your keys

# 2. Get the Express docs and build the index
git clone --depth 1 https://github.com/expressjs/expressjs.com.git ../external/expressjs.com
python -m scripts.ingest --source ../external/expressjs.com/en

# 3. Serve
uvicorn app.main:app --reload --port 8000

# 4. Frontend (new terminal)
cd ../frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000.

## Eval

```bash
cd backend
python -m eval.run_eval                  # full run + report
python -m eval.run_eval --check-thresholds  # CI mode (non-zero on regression)
```

Reports land in `backend/eval/reports/`. See [`docs/EVAL.md`](docs/EVAL.md) for what each metric means and how thresholds are set.

## Deployment

- **Backend** → Render (Docker). See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
- **Frontend** → Vercel (Next.js). Set `NEXT_PUBLIC_API_BASE_URL` to the Render URL.

## License

MIT
