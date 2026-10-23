# Deployment

The backend runs as a container. The frontend runs on any Next.js host. The two are
connected by one setting: `NEXT_PUBLIC_API_BASE_URL`.

## How the index is produced

The backend answers questions from an index built ahead of time from the GPO 2018
Annual Report PDF. Build it once, then ship it with the backend.

```bash
# Put the report at the repo root as GPO-Anual-report.pdf, then:
cd backend
python -m scripts.ingest --source ../GPO-Anual-report.pdf
```

This writes three files to `backend/data/`:

- `chroma/` — the vector store (collection `gpo_report`)
- `bm25.pkl` — the BM25 keyword index
- `docs_meta.json` — the full record for every chunk

The server needs all three to answer questions.

## Backend (container)

The backend ships a `Dockerfile` in `backend/`. It installs the dependencies, copies the
app, and copies `backend/data/` into the image, so the image serves the index you built.
It listens on `$PORT` and defaults to `8000`.

1. Build the index (above) so `backend/data/` is filled in.
2. Build the image:

   ```bash
   cd backend
   docker build -t gpo-report-rag .
   ```

3. Run it with your settings:

   ```bash
   docker run -p 8000:8000 \
     -e LLM_PROVIDER=gemini \
     -e GEMINI_API_KEY=... \
     -e COHERE_API_KEY=... \
     -e ENVIRONMENT=prod \
     -e CORS_ORIGINS=https://<your-frontend-domain> \
     gpo-report-rag
   ```

You can run the same image on any container host. Point the host's health check at
`/health`.

If your host does not keep files between restarts, that is fine: the index is baked into
the image, so nothing needs to be written at runtime.

### Backend environment variables

| Variable | Purpose |
| --- | --- |
| `LLM_PROVIDER` | `gemini` (default) or `openai` |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Used when `LLM_PROVIDER=gemini` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Used when `LLM_PROVIDER=openai` |
| `EMBEDDING_BACKEND` | `local` (default) or `openai`. Must match what the index was built with |
| `RERANKER_ENABLED` | `true` (default) or `false` |
| `COHERE_API_KEY` | Needed when the reranker is enabled |
| `TOP_K_DENSE` / `TOP_K_BM25` / `TOP_K_RERANK` | Retrieval sizes |
| `HYBRID_ALPHA` | Blend between BM25 (`0.0`) and dense (`1.0`) |
| `ENVIRONMENT` | `dev` or `prod` |
| `CORS_ORIGINS` | The frontend origin(s) allowed to call the backend |

Keep API keys in the host's secret or environment settings, not in the image or the repo.

## Frontend (Next.js host)

Deploy the `frontend/` directory to any host that runs Next.js 14.

1. Set the project root to `frontend`.
2. Use the standard Next.js build (`npm run build`) and start (`npm run start`) commands.
3. Set the environment variable:

   ```
   NEXT_PUBLIC_API_BASE_URL=https://<your-backend-domain>
   ```

4. Deploy.

Then set `CORS_ORIGINS` on the backend to the frontend's URL and restart the backend.

## Custom domains

With one apex domain, a typical layout is:

- Frontend: `yourdomain.com`
- Backend: `api.yourdomain.com`
- `NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com` on the frontend
- `CORS_ORIGINS=https://yourdomain.com` on the backend

## Verify the deploy

```bash
curl https://<your-backend-domain>/health
# {"status":"ok","indexed_chunks":<n>,...}
```

`indexed_chunks` should be greater than 0. Then open the frontend, ask a question, and
confirm the answer and its sources appear.

## Troubleshooting

- **`status` is `degraded` or `indexed_chunks` is 0**: the image was built without
  `backend/data/` filled in. Run the ingest step, then rebuild the image.
- **Frontend shows the backend as offline**: check `NEXT_PUBLIC_API_BASE_URL` and that
  `CORS_ORIGINS` on the backend matches the frontend's exact origin.
- **Answers look unrelated to the question**: confirm `EMBEDDING_BACKEND` matches what
  was used when the index was built.
- **Settings changes have no effect**: restart the backend; settings are read at startup.
