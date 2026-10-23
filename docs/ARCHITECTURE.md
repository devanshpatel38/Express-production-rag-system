# Architecture

**Built by:** [Devansh Patel](https://portfolio-website-umber-ten-90.vercel.app/#)

A retrieval-augmented chatbot grounded in the World Bank **Global Economic Prospects**
report. The report is a PDF full of prose, data tables, and figures. The system turns
it into a searchable index ahead of time, then answers questions from that index with
exact figures, units, and page citations.

```
 PDF ──► ingestion ──► Chroma + BM25 + docs_meta.json
                                   │
 question ──► hybrid search ──► rerank ──► LLM ──► answer + sources
```

## 1. Ingestion

Run once with `python -m scripts.ingest --source ../GEP-Jun-2026.pdf`. It rebuilds the
whole index each time.

### 1.1 Read the PDF

`pdf_loader.py` opens the PDF with PyMuPDF and works page by page. The 1-based PDF page
number is kept as the page number for everything produced from that page. A first pass
collects the lines that repeat at the top and bottom of pages; a second pass builds each
page's content.

### 1.2 Clean the text

`pdf_text.py` repairs what PDF extraction gets wrong: garbled (mojibake) characters,
words hyphenated across line breaks (rejoined), letter-spaced headers, and uneven
whitespace.

### 1.3 Follow the reading order

`pdf_layout.py` reassembles multi-column pages in real reading order: the left column,
then the right. Full-width titles stay where they are, so a heading still sits above
the text it introduces.

### 1.4 Strip running headers and footers

Lines that repeat on at least `HEADER_FOOTER_MIN_RECURRENCE` pages (the chapter banner,
the page number) are removed so they don't pollute the content. The section each page
belongs to is kept as context for its chunks.

### 1.5 Tables to row records

`pdf_tables.py` finds data tables and validates them, rejecting page-layout look-alikes
such as org charts. The table's title and units are read from the text around it. Each
row is then flattened into a self-contained key-value record, for example
`Region | 2025e: 4.1 | 2026f: 4.0 | …`, carrying the table's title, units, and page. A
single figure is never separated from what it means. Text inside a table region is
removed from the prose so cells are not indexed twice.

### 1.6 Figures

`pdf_figures.py` detects figure regions from their captions and renders each one.
`rag/vision.py` sends the image to a vision-capable LLM (Gemini or OpenAI, following
`LLM_PROVIDER`) with a strict instruction: report a number only if it is printed on the
figure, quoted exactly. The description is stored as a short chunk tied to its page.
`VISION_ENABLED` and the `--no-vision` flag control whether figures are described.

### 1.7 Chunk the prose

`pdf_chunker.py` splits narrative text into overlapping windows of `CHUNK_SIZE`
characters with `CHUNK_OVERLAP` overlap, each keeping its section and page. It also
produces the table-row and figure chunks. Every chunk has a type: `prose`, `table_row`,
or `figure`.

### 1.8 Index

`indexer.py` embeds every chunk and writes three artifacts:

| Path (under `backend/data/`) | Contents |
|---|---|
| `chroma/` | Chroma persistent vector store (cosine similarity) |
| `bm25.pkl` | BM25 index pickle (`{bm25, ids}`) |
| `docs_meta.json` | chunk id → full chunk record: text, title, section, page, units, chunk type |

All three must exist before the server handles requests.

## 2. Query path

```
POST /chat  or  POST /chat/stream
  └─ HybridRetriever.retrieve(query)
       ├─ dense:  embed(query) → Chroma top-K
       ├─ sparse: tokenise → BM25 top-K
       └─ fuse:   min-max normalise both, weighted sum
  └─ Reranker.rerank(query, candidates, k)
  └─ Generator.generate / stream(query, top-k chunks, history)
```

### 2.1 Hybrid retrieval

`rag/retriever.py` runs two searches over the same query. Dense search finds
paraphrases and related wording; BM25 finds exact tokens such as country names and
indicator names. Each list is min-max normalised to the range 0 to 1, then combined as
`alpha × dense + (1 − alpha) × bm25`. The single `HYBRID_ALPHA` knob sets the blend:
`0.0` is pure BM25, `1.0` is pure dense, `0.5` is the default. `TOP_K_DENSE` and
`TOP_K_BM25` set how many candidates each side contributes. The fused ids are looked up
in `docs_meta.json` to get full chunks with page, units, and type.

### 2.2 Rerank

`rag/reranker.py` sends the candidates to Cohere's cross-encoder, which scores each one
against the question and keeps the best `TOP_K_RERANK` (default 5). Page, units, and
chunk type are carried through the rerank. `RERANKER_ENABLED` turns this step on or off;
when it is off, the top fused candidates go straight to the LLM.

### 2.3 Generate

`rag/generator.py` provides one interface with a Gemini implementation (default) and an
OpenAI implementation, chosen by `LLM_PROVIDER`. The same prompt is used for both. The
model answers using only the chunks it is given, states the units and page for every
figure, and cites inline. Recent chat history is included so follow-up questions work.

### 2.4 Serving

- `POST /chat` returns `{answer, sources, latency_ms}`.
- `POST /chat/stream` is Server-Sent Events: `token` events carry answer fragments, then
  a `final` event carries the full answer, the sources (page, units, score, snippet),
  and latency. An `error` event reports failures.
- `GET /health` reports service status.

The retriever, reranker, embedder, and generator are cached singletons created on the
first request. `rag/idle_manager.py` releases them after `IDLE_TIMEOUT_SECONDS` without
a request and they reload on the next one. Changing settings needs a restart.

## 3. Embeddings

`rag/embeddings.py` provides one interface with two backends: local
sentence-transformers (`all-MiniLM-L6-v2`, the default, no API key) and OpenAI
(`text-embedding-3-small`), selected by `EMBEDDING_BACKEND`. Ingestion and queries must
use the same backend.

## 4. Evaluation

`eval/run_eval.py` runs the live pipeline over `eval/dataset.json`, a verified gold Q&A
set, and scores it two ways:

- **Ragas:** faithfulness, answer relevancy, context precision, context recall.
- **Retrieval hit-rate:** the share of questions where the retrieved chunks include a
  reference page.

Reports are written to `backend/eval/reports/`. With `--check-thresholds` the run exits
non-zero if any Ragas metric falls below its floor (faithfulness 0.70, answer relevancy
0.70, context precision 0.55, context recall 0.55). GitHub Actions runs this check on
pull requests.

## 5. Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (Python 3.11) |
| PDF parsing | PyMuPDF |
| Vector store | ChromaDB (persistent) |
| Sparse retrieval | rank_bm25 |
| Embeddings | sentence-transformers (default), OpenAI (optional) |
| Reranker | Cohere Rerank |
| LLM | Gemini (default) / OpenAI |
| Transport | REST `/chat` + SSE `/chat/stream` |
| Eval | Ragas |
| Frontend | Next.js 14 (App Router) |
| CI | GitHub Actions |

## License

MIT
