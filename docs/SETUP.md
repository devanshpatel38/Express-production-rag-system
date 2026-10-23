# Setup

Local setup from scratch. Deployment is in [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Prerequisites

- Python 3.11
- Node 20+
- Git
- The report PDF: `GEP-Jun-2026.pdf` (World Bank Global Economic Prospects)
- An API key for **one** LLM provider:
  - [Gemini](https://aistudio.google.com/apikey) (default)
  - [OpenAI](https://platform.openai.com/api-keys)
- A [Cohere](https://dashboard.cohere.com/api-keys) API key for the reranker

## 1. Clone

```bash
git clone <your-repo-url>
cd <your-repo-folder>
```

## 2. Backend

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
COHERE_API_KEY=...
```

To use OpenAI instead, set `LLM_PROVIDER=openai` and `OPENAI_API_KEY=...`
(`OPENAI_MODEL` picks the model).

Settings you can change in `.env`:

| Variable | What it does |
| --- | --- |
| `LLM_PROVIDER` | `gemini` (default) or `openai` |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini key and model |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | OpenAI key and model |
| `EMBEDDING_BACKEND` | `local` (sentence-transformers MiniLM, default) or `openai` |
| `RERANKER_ENABLED`, `COHERE_API_KEY` | Turn the Cohere reranker on or off, and its key |
| `CHUNK_SIZE`, `CHUNK_OVERLAP` | Size and overlap of the prose chunks |
| `TOP_K_DENSE`, `TOP_K_BM25` | Candidates from each retriever before blending |
| `TOP_K_RERANK` | How many chunks reach the LLM prompt |
| `HYBRID_ALPHA` | Blend weight: `0.0` = pure BM25, `1.0` = pure dense, `0.5` default |
| `CORS_ORIGINS` | Allowed frontend origin (default `http://localhost:3000`) |

With the local embedding backend, the sentence-transformers model (about 80MB)
downloads on the first run.

The index is stored in `backend/data/chroma/`, `backend/data/bm25.pkl` and
`backend/data/docs_meta.json`. The vector collection is named `gep_report`.

## 3. Add the report PDF

Place the report at the repo root as `GEP-Jun-2026.pdf`:

```
<repo root>/
├── GEP-Jun-2026.pdf
├── backend/
└── frontend/
```

## 4. Build the index

```bash
cd backend
python -m scripts.ingest --source ../GEP-Jun-2026.pdf
```

The script reads the PDF, cleans the text, turns tables into per-row records,
describes the figures, chunks the prose, and writes the vector store and BM25
index into `backend/data/`. Each run rebuilds the index from scratch.

Figure descriptions use your configured LLM, so the key from step 2 must be set.

For a quick trial on part of the report, add `--max-pages N`.

## 5. Serve

```bash
# Still in backend/
uvicorn app.main:app --reload --port 8000
```

Check that it is up:

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is the 2026 GDP growth forecast for Sub-Saharan Africa?"}'
```

`/health` reports `status: ok` and the number of indexed chunks once the index
is in place. API docs are at http://localhost:8000/docs.

Settings load once at startup, so restart the server after editing `.env`.

## 6. Frontend

In a new terminal:

```bash
cd frontend
npm install
cp .env.example .env.local
```

`.env.local` needs:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Then start it:

```bash
npm run dev
```

Open http://localhost:3000.

Other frontend commands: `npm run build`, `npm run typecheck`, `npm run lint`.

## 7. Run the eval (optional)

```bash
cd backend
python -m eval.run_eval
```

This prints the Ragas metrics and saves a report to `backend/eval/reports/`.
Ragas needs a scoring LLM: set `OPENAI_API_KEY`, or set `GEMINI_API_KEY`
(`langchain-google-genai` is in `requirements.txt`).

## Troubleshooting

- **`/health` shows `degraded` or `/chat` says the index is not ready**:
  run the ingest step (step 4) from the `backend/` folder. Paths like
  `./data/` are relative to where you run the command.
- **Ingest cannot find the PDF**: check that `GEP-Jun-2026.pdf` is at the repo
  root and that you passed `--source ../GEP-Jun-2026.pdf` from `backend/`.
- **Frontend shows "backend offline"**: check that uvicorn is running on port
  8000 and that `NEXT_PUBLIC_API_BASE_URL` matches it. Restart `npm run dev`
  after changing `.env.local`.
- **Browser CORS errors**: make sure `CORS_ORIGINS` in `backend/.env` includes
  the exact origin of the frontend, then restart the backend.
- **Cohere 429 errors**: the reranker free tier is rate-limited. Set
  `RERANKER_ENABLED=false` for heavy local runs.
- **Out of memory on ingest**: close other apps or lower `CHUNK_SIZE`.
