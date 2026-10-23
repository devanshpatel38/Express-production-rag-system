# Global Economic Prospects RAG

**Built by:** [Devansh Patel](https://portfolio-website-umber-ten-90.vercel.app/#)

A retrieval-augmented chatbot grounded in the World Bank's **Global Economic Prospects**
report. Ask it a question and it answers from the report itself — pulling exact figures
straight out of the data tables ("what's the 2026 GDP growth forecast for Sub-Saharan
Africa?") as well as the narrative ("what are the main risks to the global outlook?").
Every answer cites the page it came from and the units the figure is in.

## How it works

```
  question
     │
     ▼
  hybrid search         dense embeddings (Chroma) + BM25 keyword search, blended
     │
     ▼
  rerank                Cohere cross-encoder picks the few best-matching chunks
     │
     ▼
  generate              the LLM answers using only those chunks, citing page + units
     │
     ▼
  answer + sources      streamed to the UI, with a sources panel (page, units, score)
```

The report is turned into a searchable index ahead of time (the **ingestion** step
below). At question time the system searches that index, reranks the matches down to
the most relevant handful, and the LLM writes a grounded answer from them — quoting
figures exactly and naming their page and units.

## Ingestion strategy

A 200-page economic report is mostly prose, but the valuable numbers live in dense
data tables and figures. The ingestion pipeline reads the PDF and prepares each kind
of content so it can be retrieved cleanly:

1. **Read the PDF and clean the text.** Repair the garbled characters that PDF
   extraction produces, rejoin words broken across line endings, and collapse the odd
   letter- and word-spacing so the text reads normally.
2. **Follow the real reading order.** Many pages are two-column; the text is reassembled
   left column then right column so sentences stay in order, with full-width titles
   kept in place.
3. **Drop the running headers and footers.** The chapter banner and page number that
   repeat on every page are detected and removed so they don't pollute the content,
   while the section each page belongs to is kept as context.
4. **Turn tables into per-row records.** Each data table is detected, validated (so page
   layouts like org charts aren't mistaken for data), and every row is flattened into a
   self-contained `Region | 2025e: 4.1 | 2026f: 4.0 | …` record. Each record carries the
   table's title, its **units** (e.g. "percent, annual"), and its **page**, so a single
   figure is never separated from what it means.
5. **Describe the figures.** Charts and figures are read for the values printed on them,
   captured as short descriptions tied to their page.
6. **Chunk the prose.** The narrative text is split into overlapping windows that keep
   their section and page, so explanations aren't cut mid-thought.

Everything — prose, table rows, and figures — is embedded into the vector store and a
BM25 index, each piece tagged with its page and units for precise, citable retrieval.

## Tech stack

| Layer | Choice |
| --- | --- |
| Backend | FastAPI (Python 3.11) |
| PDF parsing | PyMuPDF |
| Vector store | ChromaDB (persistent) |
| Sparse retrieval | rank_bm25 |
| Embeddings | sentence-transformers (default), OpenAI (optional) |
| Reranker | Cohere Rerank |
| LLM | Gemini (default) / OpenAI, one interface, chosen by env var |
| Transport | REST `/chat` + SSE `/chat/stream` (token + source streaming) |
| Eval | Ragas (faithfulness, answer relevancy, context precision/recall) |
| Frontend | Next.js 14 (App Router) |
| CI | GitHub Actions |

## Quickstart

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in your API keys

# 2. Put the report PDF at the repo root as GEP-Jun-2026.pdf, then build the index
python -m scripts.ingest --source ../GEP-Jun-2026.pdf

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
python -m eval.run_eval                     # full run + report
python -m eval.run_eval --check-thresholds  # CI mode (non-zero exit on regression)
```

Reports land in `backend/eval/reports/`. Scores are checked against thresholds on every
pull request via GitHub Actions.

## License

MIT
