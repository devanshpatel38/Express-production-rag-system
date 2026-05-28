# Deployment

Backend on Render, frontend on Vercel. Both have free tiers that comfortably
host this project.

## Backend → Render

The backend ships a `Dockerfile`; Render builds and runs it directly.

### One-off: build the index locally and commit it

Render's filesystem is ephemeral on free instances — anything written at runtime
disappears on restart. For a docs corpus this small (~1MB of indices), the
simplest path is to **ingest locally, commit `backend/data/`, and let Render
serve those files**.

```bash
cd backend
python -m scripts.ingest --source ../external/expressjs.com/en

# Allow data/ in git for the deploy commit:
git add -f data/chroma data/bm25.pkl data/docs_meta.json
git commit -m "chore: ship pre-built index"
git push
```

(If you don't want indices in git, the alternative is a build-time ingestion
step in `render.yaml` — but you'll pay the embed cost on every deploy.)

### Create the service

1. Push the repo to GitHub.
2. Render → **New** → **Web Service** → connect the repo.
3. Settings:
   - **Environment**: Docker
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Health Check Path**: `/health`
4. Environment variables (copy from your local `.env`):
   - `LLM_PROVIDER=gemini`
   - `GEMINI_API_KEY=...`
   - `COHERE_API_KEY=...` (optional)
   - `CORS_ORIGINS=https://<your-vercel-domain>.vercel.app`
5. Deploy. First build takes ~5 min (PyTorch wheel is large).

The service will be live at `https://<service-name>.onrender.com`.

### Free-tier caveats

- Render free instances **spin down after 15 min of inactivity**. The first
  request after that takes 30–60s to wake up. The frontend handles this by
  showing the "backend offline" pill until /health resolves.
- 512MB RAM. Sentence-transformers' MiniLM loads at ~250MB which fits, but
  if you bump to a bigger embedding model you'll need a paid plan.

## Frontend → Vercel

1. Push the repo.
2. Vercel → **Add New** → **Project** → import the repo.
3. Settings:
   - **Framework Preset**: Next.js (auto-detected)
   - **Root Directory**: `frontend`
4. Environment variable:
   - `NEXT_PUBLIC_API_BASE_URL=https://<your-render-service>.onrender.com`
5. Deploy.

Vercel will give you `https://<project>.vercel.app`. Add this URL to
`CORS_ORIGINS` on the Render service and redeploy the backend.

## Custom domain

Both Render and Vercel make this two clicks each. If you're using a single
apex domain (e.g. `yourdomain.com`):

- Frontend: `yourdomain.com` → Vercel (CNAME or A records)
- Backend: `api.yourdomain.com` → Render (CNAME)
- Update `NEXT_PUBLIC_API_BASE_URL` on Vercel to `https://api.yourdomain.com`
- Update `CORS_ORIGINS` on Render to `https://yourdomain.com`

## After deploy: verify

```bash
curl https://api.yourdomain.com/health
# Should show indexed_chunks > 0
```

Open the frontend URL, ask a question, confirm sources render. If you see
"backend offline", the Render service is asleep or CORS is misconfigured —
check the browser network tab.
