# Express Docs RAG

**Built by:** [Devansh Patel](https://portfolio-website-umber-ten-90.vercel.app/#)

A retrieval-augmented chatbot grounded in the official Express.js documentation.
Built to demonstrate a production-shaped RAG pipeline end-to-end, not a notebook demo.


## What's inside

- **Hybrid retrieval** — dense embeddings (Chroma) fused with BM25, single `alpha` knob to control the blend
- **Cross-encoder reranking** — Cohere Rerank narrows the top-k that actually reaches the LLM
- **Eval harness** — Ragas (faithfulness, answer relevancy, context precision/recall) over a hand-curated Q&A set
- **GitHub Actions** — eval runs on every PR and fails the build if scores drop below configured thresholds
- **Multi-provider LLM** — Gemini and OpenAI behind one interface; provider chosen by env var
- **Sourced answers** — every response carries inline citations and an expandable sources panel

## Architecture at a glance

```
                ┌──────────────┐
   query ──────▶│  Hybrid      │   dense (Chroma + MiniLM)
                │  Retriever   │   sparse (rank_bm25)
                └──────┬───────┘
                       │ top 30 (15 dense + 15 BM25, min-max fused)
                       ▼
                ┌──────────────┐
                │  Reranker    │   Cohere rerank-english-v3.0
                └──────┬───────┘
                       │ top 5
                       ▼
                ┌──────────────┐
                │  Generator   │   Gemini / OpenAI
                └──────┬───────┘
                       │
                       ▼ answer + sources
```

More detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | FastAPI (Python 3.11) | Async, typed, clean OpenAPI |
| Vector store | ChromaDB (persistent) | Embedded, no extra service |
| Sparse retrieval | rank_bm25 | Pure-Python, no Lucene/ES |
| Embeddings | sentence-transformers (default), OpenAI (optional) | Free dev, scalable swap |
| Reranker | Cohere Rerank v3 | Best quality/effort ratio |
| LLM | Gemini 1.5 Flash (default), GPT-4o-mini | Cheap, fast, swappable |
| Eval | Ragas + custom retrieval hit-rate | Standard metrics + sanity |
| Frontend | Next.js 14 + Tailwind | Editorial UI, type-safe |
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
