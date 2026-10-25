# Setup

Step by step, from a fresh clone to a running chatbot.

## Prerequisites

- Python 3.11
- Node.js 20
- A Gemini API key (default) or an OpenAI API key
- Optional: a Cohere API key for reranking

The report PDF, `iMac_PER_Oct2024.pdf`, sits in the repo root.

## 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill in:

| Key | Notes |
| --- | --- |
| `LLM_PROVIDER` | `gemini` (default) or `openai` |
| `GEMINI_API_KEY` | needed when the provider is `gemini` |
| `OPENAI_API_KEY` | needed when the provider is `openai` |
| `COHERE_API_KEY` | optional; without it reranking passes the order through |
| `RERANKER_ENABLED` | `true` by default; set `false` to skip reranking |
| `EMBEDDING_BACKEND` | `local` by default (no key; downloads about 80 MB the first time) |
| `SOURCE_PDF_PATH` | `../iMac_PER_Oct2024.pdf` by default |

## 2. Build the index

```bash
python -m scripts.ingest
```

`--source` defaults to `SOURCE_PDF_PATH` (`../iMac_PER_Oct2024.pdf`). To point at another
copy: `python -m scripts.ingest --source path/to/report.pdf`.

The script prints the page count and the chunk counts (prose and table rows), then writes:

- `data/chroma/`
- `data/bm25.pkl`
- `data/docs_meta.json`

The report produces 50 chunks over 12 pages. These three files must exist before the server
can answer questions.

## 3. Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

Check it:

```bash
curl http://localhost:8000/health
# {"status":"ok","indexed_chunks":50, ...}
```

## 4. Frontend

In a new terminal:

```bash
cd frontend
npm install
cp .env.example .env.local     # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000 and ask something like "How much electricity does the iMac use
in sleep mode?". The sources panel shows the page and units behind the answer.

Other frontend commands: `npm run build`, `npm run typecheck`, `npm run lint`.

## 5. Tests and eval

```bash
cd backend
pytest
python -m eval.run_eval
```

See [`EVAL.md`](EVAL.md) for the eval and its scoring key.

## Troubleshooting

- **`status: degraded` on /health** - the index has not been built. Run step 2.
- **"Index not ready" in the chat** - same cause; run `python -m scripts.ingest`.
- **Browser shows "backend offline"** - check that uvicorn is running and that
  `CORS_ORIGINS` in `.env` includes `http://localhost:3000`.
- **Changed `.env`** - restart uvicorn; settings are read once at the first request.
