# Deployment

Backend on Render (Docker), frontend on Vercel.

## Backend on Render

The backend ships a `Dockerfile`; Render builds and runs it directly. The image copies
`backend/data/`, so the built index goes into the image.

### Build the index and commit it

Render's disk is ephemeral, so build the index locally and ship the files. The index for the
12-page report is tiny.

```bash
cd backend
python -m scripts.ingest

# data/ is ignored by git; add it explicitly for the deploy commit
git add -f data/chroma data/bm25.pkl data/docs_meta.json
git commit -m "chore: ship pre-built index"
git push
```

### Create the service

1. Push the repo to GitHub.
2. Render: **New** > **Web Service** > connect the repo.
3. Settings:
   - **Environment**: Docker
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Health Check Path**: `/health`
4. Environment variables (copy from your local `.env`):
   - `LLM_PROVIDER=gemini`
   - `GEMINI_API_KEY=...`
   - `COHERE_API_KEY=...` (optional)
   - `CORS_ORIGINS=https://<your-vercel-domain>`
5. Deploy. The first build takes a few minutes because the PyTorch wheel is large.

The service is served at `https://<service-name>.onrender.com`. The container listens on
`$PORT`, which Render sets.

### Memory

The local MiniLM embedding model uses roughly 250 MB. Size the instance to fit it, or set
`EMBEDDING_BACKEND=openai` and rebuild the index with the same setting.

## Frontend on Vercel

1. Push the repo.
2. Vercel: **Add New** > **Project** > import the repo.
3. Settings:
   - **Framework Preset**: Next.js
   - **Root Directory**: `frontend`
4. Environment variable:
   - `NEXT_PUBLIC_API_BASE_URL=https://<your-render-service>.onrender.com`
5. Deploy.

Add the Vercel domain to `CORS_ORIGINS` on the Render service and redeploy the backend.

## Custom domain

With a single apex domain such as `yourdomain.com`:

- Frontend: `yourdomain.com` points to Vercel.
- Backend: `api.yourdomain.com` points to Render.
- Set `NEXT_PUBLIC_API_BASE_URL` on Vercel to `https://api.yourdomain.com`.
- Set `CORS_ORIGINS` on Render to `https://yourdomain.com`.

## Verify

```bash
curl https://api.yourdomain.com/health
# indexed_chunks should be 50
```

Open the frontend, ask a question, and confirm the answer cites a page and the sources panel
shows page and units. If the page shows "backend offline", check that the backend is running
and that `CORS_ORIGINS` matches the frontend domain.
