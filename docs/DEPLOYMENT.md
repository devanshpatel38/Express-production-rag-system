# Deployment

The system has two parts: a containerized FastAPI backend that serves a
pre-built index, and a Next.js frontend on any Next.js host. Local setup is in
[`SETUP.md`](SETUP.md).

## How the index is produced

The backend answers questions from three artifacts in `backend/data/`:

- `chroma/` — the Chroma vector store (collection `gep_report`)
- `bm25.pkl` — the BM25 index
- `docs_meta.json` — chunk records used when blending results

Build them from the report PDF, from the `backend/` folder:

```bash
cd backend
python -m scripts.ingest --source ../GEP-Jun-2026.pdf
```

The backend image copies `backend/data/` into the container, so build the index
before building the image. Then check it:

```bash
uvicorn app.main:app --port 8000
curl http://localhost:8000/health      # indexed chunks should be > 0
```

The embedding backend used at ingest time (`EMBEDDING_BACKEND`) must be the
same one the deployed backend uses, so the query vectors match the stored ones.

## Backend

The backend ships a `Dockerfile` (Python 3.11) that installs the requirements,
copies `app/`, `eval/`, `scripts/` and `data/`, and runs:

```
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

It listens on `$PORT`, defaulting to 8000.

```bash
cd backend
docker build -t gep-rag-backend .
docker run -p 8000:8000 --env-file .env gep-rag-backend
```

Any container host works. Point the host at the `backend/` folder, use the
Dockerfile, and set `/health` as the health check path.

### Environment variables

Set these on the backend host (same names as `backend/.env.example`):

| Variable | Purpose |
| --- | --- |
| `ENVIRONMENT` | `dev` or `prod` |
| `CORS_ORIGINS` | The frontend's public origin, e.g. `https://<your-frontend-domain>` |
| `LLM_PROVIDER` | `gemini` (default) or `openai` |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Used when the provider is `gemini` |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Used when the provider is `openai` (also for OpenAI embeddings) |
| `EMBEDDING_BACKEND` | `local` (default) or `openai` |
| `RERANKER_ENABLED`, `COHERE_API_KEY` | Cohere reranker switch and key |
| `CHUNK_SIZE`, `CHUNK_OVERLAP` | Chunking settings |
| `TOP_K_DENSE`, `TOP_K_BM25`, `TOP_K_RERANK` | Retrieval sizes |
| `HYBRID_ALPHA` | Dense/BM25 blend (`0.0` to `1.0`) |

Keep API keys in the host's secret or environment settings, not in the repo.
Settings load once at startup, so redeploy or restart after changing them.

### Sizing notes

- With `EMBEDDING_BACKEND=local`, the MiniLM model (about 80MB) loads in
  memory and downloads on first start. Allow room for it plus PyTorch.
- The first image build takes a few minutes because PyTorch is large.

## Frontend

Deploy `frontend/` to any host that runs Next.js 14.

1. Set the project root to `frontend`.
2. Use the standard Next.js build (`npm run build`) and start (`npm start`)
   commands, or your host's built-in Next.js preset.
3. Set the environment variable:

   ```
   NEXT_PUBLIC_API_BASE_URL=https://<your-backend-domain>
   ```

   This value is read at build time, so rebuild the frontend after changing it.
4. Add the frontend's public URL to `CORS_ORIGINS` on the backend and
   redeploy the backend.

## Custom domains

If you use one domain for both parts:

- Frontend: `yourdomain.com`
- Backend: `api.yourdomain.com`
- `NEXT_PUBLIC_API_BASE_URL` on the frontend: `https://api.yourdomain.com`
- `CORS_ORIGINS` on the backend: `https://yourdomain.com`

## Verify

```bash
curl https://api.yourdomain.com/health
# status "ok" and indexed chunks > 0
```

Open the frontend URL, ask a question such as "What is the 2026 GDP growth
forecast for Sub-Saharan Africa?", and confirm the answer streams in and the
sources panel shows the page and units. If the UI shows "backend offline",
check that the backend is running, `NEXT_PUBLIC_API_BASE_URL` is correct, and
`CORS_ORIGINS` includes the frontend origin.

## Updating the report or settings

To change the report or chunking settings, re-run the ingest step, rebuild the
backend image so it carries the new `backend/data/`, and redeploy.
