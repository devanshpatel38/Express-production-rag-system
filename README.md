# GPO Annual Report RAG

**Built by:** [Devansh Patel](https://portfolio-website-umber-ten-90.vercel.app/#)

A retrieval-augmented chatbot grounded in the **U.S. Government Publishing Office (GPO)
2018 Annual Report**. Ask it a question and it answers from the report itself — pulling
exact figures straight out of the financial statements ("what were GPO's billings to the
Department of State in 2018?") as well as the narrative ("what were GPO's main priorities
and accomplishments?"). Every answer cites the page it came from and the units the figure
is in.

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
below). At question time the system searches that index, reranks the matches down to the
most relevant handful, and the LLM writes a grounded answer from them — quoting figures
exactly and naming their page and units.

## Ingestion strategy

A government annual report mixes narrative sections, formal letters, and dense financial
statements. The ingestion pipeline reads the PDF and prepares each kind of content so it
can be retrieved cleanly:

1. **Read the PDF and clean the text.** Repair the garbled characters that PDF extraction
   produces, rejoin words broken across line endings, and collapse the letter-spaced
   headings (e.g. `G O V E R N M E N T` → `GOVERNMENT`) and odd whitespace so the text
   reads normally.
2. **Follow the real reading order.** Multi-column pages are reassembled left column then
   right column so sentences stay in order, with full-width titles kept in place.
3. **Drop the running headers and footers.** The section banner and page number that
   repeat across pages are detected and removed so they don't pollute the content, while
   the section each page belongs to is kept as context.
4. **Turn financial tables into per-row records.** Each table is detected and validated
   (so page layouts like org charts aren't mistaken for data), its stacked cells are split
   back into individual rows, and every row is flattened into a self-contained
   `U.S. Department of State | 2018: $270,596 | 2017: $310,971` record. Each record carries
   the table's descriptor, its **units** (e.g. "Dollars in thousands"), and its **page**,
   so a single figure is never separated from what it means.
5. **Chunk the prose.** The narrative text is split into overlapping windows that keep
   their section and page, so explanations aren't cut mid-thought.

Everything — prose and table rows — is embedded into the vector store and a BM25 index,
each piece tagged with its page and units for precise, citable retrieval.

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

# 2. Put the report PDF at the repo root as GPO-Anual-report.pdf, then build the index
python -m scripts.ingest --source ../GPO-Anual-report.pdf

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
