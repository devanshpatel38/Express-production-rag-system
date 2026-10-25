# iMac Report RAG

**Built by:** [Devansh Patel](https://portfolio-website-umber-ten-90.vercel.app/#)

A chatbot that answers questions about Apple's **iMac Product Environmental Report**
(`iMac_PER_Oct2024.pdf`, a 12-page PDF). Ask about the carbon footprint, energy use,
materials or packaging, and it answers only from the report, tells you which page the
answer came from, and includes the units of every figure.

The pipeline is simple: **retrieve, rerank, generate**. Answers stream to the browser
as they are written.

## How it works

```
  question
     |
     v
 1. Hybrid retrieval   dense vectors + BM25 keyword search, blended by one knob
     |
     v
 2. Reranking          a Cohere cross-encoder re-orders the candidates, keeps the best
     |
     v
 3. Generation         Gemini or OpenAI answers from those chunks only, cites page + units
     |
     v
 answer + sources (page, units, chunk type)
```

1. **Hybrid retrieval.** The question is searched two ways. Dense search turns it into a
   384-number vector (local sentence-transformers MiniLM) and finds the closest chunks in
   ChromaDB. BM25 search matches exact words, which helps with terms like "kWh" or "CO2e".
   Both score lists are squeezed to a 0-1 range (min-max) and blended with a single knob,
   `HYBRID_ALPHA`.
2. **Reranking.** A Cohere cross-encoder reads the question together with each candidate
   and re-orders them by how well they really answer it. Only the top few go on to the
   model. Without a Cohere key this step passes the fused order through unchanged.
3. **Generation.** Gemini (default) or OpenAI, behind one interface, writes the answer using
   only the retrieved context. The answer cites the page number and the units of each figure.

## How the PDF is ingested

The PDF is read **prose-first** with PyMuPDF, then turned into 50 searchable chunks over
the 12 pages.

- **Clean text extraction.** Text is read span by span. Tiny superscript footnote markers
  are dropped so key terms stay clean ("electricity9" becomes "electricity"), while real
  figures such as "391 kg CO2e" are kept.
- **Text normalization.** Garbled characters are repaired, non-breaking spaces become normal
  spaces, words split by a line-end hyphen are rejoined (never across digits), and stray
  whitespace is collapsed while paragraphs are kept.
- **Running header removal.** The repeating "iMac | Product Environmental Report N" line is
  found and removed. The running section name becomes each page's breadcrumb.
- **Reading order for columns.** On multi-column pages the column gutter is detected and the
  page is split into bands, so text is read left column, then right column, in the right order.
- **Strict table detection.** Only real grids become tables. In this report that is the
  power-consumption table (modes by 100V / 115V / 230V). Each table row becomes its own
  key-value chunk that carries its units.
- **Prose chunks.** Everything else is cut into prose chunks with a sliding window that
  overlaps, so no sentence is lost at a boundary.
- **Metadata on every chunk.** Page number (1-based), section, chunk type (prose or table
  row), units, table title and source file.

Details are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## API

| Endpoint | What it does |
| --- | --- |
| `GET /health` | Readiness probe: indexed chunk count, LLM provider, reranker status |
| `POST /chat` | Runs the pipeline and returns the full answer and sources as JSON |
| `POST /chat/stream` | Server-Sent Events: answer tokens as they are generated, then a final payload with sources |

Each source carries its page, units and chunk type.

## Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | FastAPI (Python 3.11) | Async, typed, clean OpenAPI |
| PDF parsing | PyMuPDF | Span, block and word positions for layout-aware extraction |
| Vector store | ChromaDB (persistent) | Embedded, no extra service |
| Sparse retrieval | rank_bm25 | Pure Python keyword search |
| Embeddings | sentence-transformers MiniLM (default), OpenAI (optional) | Free locally, easy to swap |
| Reranker | Cohere Rerank | Strong quality for little effort |
| LLM | Gemini (default), OpenAI | One interface, chosen by env var |
| Transport | REST `/chat` + SSE `/chat/stream` | Token streaming |
| Eval | Ragas + page-based retrieval hit-rate | Standard metrics plus a retrieval sanity check |
| Frontend | Next.js 14 (App Router) | Landing page and chat, SSE client |
| CI | GitHub Actions | Typecheck, build, eval gate |

## Quickstart

See [`docs/SETUP.md`](docs/SETUP.md) for the full steps. The short version:

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in your keys

# 2. Build the index from the PDF (defaults to ../iMac_PER_Oct2024.pdf)
python -m scripts.ingest

# 3. Serve
uvicorn app.main:app --reload --port 8000

# 4. Frontend (new terminal)
cd ../frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000.

## Eval

A Ragas harness runs the live pipeline over a hand-verified question set and scores four
metrics, plus a page-based retrieval hit-rate.

| Metric | Floor | Current |
| --- | --- | --- |
| faithfulness | 0.70 | 0.73 |
| answer_relevancy | 0.70 | 0.97 |
| context_precision | 0.55 | 0.87 |
| context_recall | 0.55 | 0.94 |
| page hit-rate | - | 100% |

```bash
cd backend
python -m eval.run_eval                     # full run + report
python -m eval.run_eval --check-thresholds  # CI mode (non-zero on regression)
```

GitHub Actions runs the eval on pull requests and fails the build if any metric drops below
its floor. Reports land in `backend/eval/reports/`. See [`docs/EVAL.md`](docs/EVAL.md).

## Deployment

- **Backend** goes to Render (Docker). See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
- **Frontend** goes to Vercel (Next.js). Set `NEXT_PUBLIC_API_BASE_URL` to the Render URL.

## License

MIT
