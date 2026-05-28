# Setup

Local dev. Deployment is in [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Prereqs

- Python 3.11+
- Node 20+
- Git
- An API key for **one** LLM provider:
  - [Gemini](https://aistudio.google.com/apikey) — free tier, default
  - [OpenAI](https://platform.openai.com/api-keys) — paid
- Optional: [Cohere](https://dashboard.cohere.com/api-keys) for the reranker (free tier covers dev)

## 1. Clone

```bash
git clone <your-fork-url> express-docs-rag
cd express-docs-rag
```

## 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Open .env and set at minimum:
#   LLM_PROVIDER=gemini
#   GEMINI_API_KEY=...
# Optionally set COHERE_API_KEY for reranking.
```

The first run will download the sentence-transformers model (~80MB).

## 3. Get the Express docs

We use the official `expressjs/expressjs.com` repo as the corpus.

```bash
# From the project root
git clone --depth 1 https://github.com/expressjs/expressjs.com.git external/expressjs.com
```

This gives you `external/expressjs.com/en/` — that's the directory we feed to
the ingest script.

## 4. Build the index

```bash
cd backend
python -m scripts.ingest --source ../external/expressjs.com/en
```

Expected output:

```
Ingesting from: /abs/path/external/expressjs.com/en
Chunk size=700, overlap=120
Processed 73 files → 1234 chunks
  embedded 64/1234
  ...
Done.
  chunks: 1234
  vector_dim: 384
  chroma_path: ./data/chroma
  bm25_path: ./data/bm25.pkl
```

The `backend/data/` directory now holds the persisted indices.

## 5. Serve

```bash
# Still in backend/
uvicorn app.main:app --reload --port 8000
```

Sanity-check:

```bash
curl http://localhost:8000/health
# {"status":"ok","indexed_chunks":1234,"llm_provider":"gemini","reranker_enabled":true}

curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"How do I define a GET route?"}'
```

## 6. Frontend

In a new terminal:

```bash
cd frontend
npm install
cp .env.example .env.local
# NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 should already be correct.
npm run dev
```

Open http://localhost:3000.

## 7. Run the eval (optional but recommended)

```bash
cd backend
python -m eval.run_eval
```

You'll see the four Ragas metrics plus retrieval hit-rate and p50 latency,
and a JSON report saved to `eval/reports/`.

## Common gotchas

- **`Index not ready` from /chat**: you didn't run ingestion (step 4), or you
  ran it in a different working directory. The script saves to `./data/`
  relative to wherever you ran it.
- **OOM on ingest**: drop `CHUNK_SIZE` or run on a machine with >4GB free.
- **`OPENAI_API_KEY missing` errors during eval**: Ragas needs a scoring LLM.
  Either set `OPENAI_API_KEY`, or make sure `GEMINI_API_KEY` is set and the
  `langchain-google-genai` package is installed (it's in requirements.txt).
- **Cohere 429s**: the reranker free tier is rate-limited. Set
  `RERANKER_ENABLED=false` to skip it during heavy local runs.
