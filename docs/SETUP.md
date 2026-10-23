# Setup

Local setup from scratch. Deployment is in [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Prerequisites

- Python 3.11+
- Node 20+
- Git
- The GPO 2018 Annual Report PDF
- An API key for **one** LLM provider:
  - [Gemini](https://aistudio.google.com/apikey) (default)
  - [OpenAI](https://platform.openai.com/api-keys)
- Optional: a [Cohere](https://dashboard.cohere.com/api-keys) API key for the reranker

## 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
```

Open `.env` and set at least:

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
```

To use OpenAI instead, set `LLM_PROVIDER=openai` and `OPENAI_API_KEY`. Set
`COHERE_API_KEY` to turn on reranking, or set `RERANKER_ENABLED=false` to skip it.

By default embeddings are computed locally with sentence-transformers
(`EMBEDDING_BACKEND=local`). The model downloads on first run. To use OpenAI
embeddings, set `EMBEDDING_BACKEND=openai` and `OPENAI_API_KEY`.

### Settings you can tune

| Variable | What it does |
| --- | --- |
| `LLM_PROVIDER` | `gemini` or `openai` |
| `GEMINI_MODEL` / `OPENAI_MODEL` | Model name for the chosen provider |
| `EMBEDDING_BACKEND` | `local` or `openai` |
| `RERANKER_ENABLED` | `true` or `false` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | Size and overlap of prose chunks, in characters |
| `TOP_K_DENSE` / `TOP_K_BM25` | Candidates each retriever returns before blending |
| `TOP_K_RERANK` | How many chunks reach the LLM prompt |
| `HYBRID_ALPHA` | Blend weight: `0.0` is BM25 only, `1.0` is dense only, `0.5` is the default |

If you change `CHUNK_SIZE`, `CHUNK_OVERLAP`, or the embedding settings, rebuild the
index (step 3).

## 2. Add the report PDF

Place the report at the repo root with this exact name:

```
GPO-Anual-report.pdf
```

## 3. Build the index

```bash
cd backend
python -m scripts.ingest --source ../GPO-Anual-report.pdf
```

This reads the PDF, cleans the text, turns each financial table into per-row records,
chunks the prose, and writes the index to `backend/data/`:

- `chroma/` — the vector store (collection `gpo_report`)
- `bm25.pkl` — the BM25 keyword index
- `docs_meta.json` — the full record for every chunk

All three files are needed before the server can answer questions.

## 4. Serve

```bash
# Still in backend/
uvicorn app.main:app --reload --port 8000
```

Check it:

```bash
curl http://localhost:8000/health
# {"status":"ok","indexed_chunks":<n>,"llm_provider":"gemini","reranker_enabled":true}

curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"What were GPO'"'"'s billings to the Department of State in 2018?"}'
```

## 5. Frontend

In a new terminal:

```bash
cd frontend
npm install
cp .env.example .env.local
# NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000.

## 6. Run the eval (optional)

```bash
cd backend
python -m eval.run_eval
```

This scores the pipeline with Ragas and saves a report to `eval/reports/`. Ragas needs
a scoring LLM: set `OPENAI_API_KEY`, or set `GEMINI_API_KEY` (the
`langchain-google-genai` package is in `requirements.txt`).

## Troubleshooting

- **`/health` shows `"status":"degraded"` or `indexed_chunks` is 0**: the index has not
  been built, or it was built from a different working directory. Run the ingest
  command from `backend/` so the files land in `backend/data/`.
- **Ingest cannot find the PDF**: check that `GPO-Anual-report.pdf` is at the repo root
  and that you ran the command from `backend/` with `--source ../GPO-Anual-report.pdf`.
- **Out of memory during ingest**: close other programs, or lower `CHUNK_SIZE`.
- **Cohere rate-limit errors (429)**: set `RERANKER_ENABLED=false` for heavy local runs.
- **Browser cannot reach the backend**: check that `NEXT_PUBLIC_API_BASE_URL` in
  `frontend/.env.local` matches the backend address, and that `CORS_ORIGINS` in
  `backend/.env` includes `http://localhost:3000`.
- **Settings changes have no effect**: restart the server; settings are read at startup.
