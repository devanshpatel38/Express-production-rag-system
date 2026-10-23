# Architecture

**Built by:** [Devansh Patel](https://portfolio-website-umber-ten-90.vercel.app/#)

A retrieval-augmented chatbot grounded in the **U.S. Government Publishing Office (GPO)
2018 Annual Report**. The system has two halves: an **ingestion** step that turns the
report PDF into a searchable index, and a **query** path that searches that index and has
an LLM write a grounded, cited answer.

## System overview

```
                    INGESTION (run once)
  PDF ──► clean text ──► reading order ──► strip headers/footers
                                              │
                         ┌────────────────────┴───────────────────┐
                         ▼                                        ▼
                 financial tables                           narrative prose
          validate → split rows → key-value records     overlapping windows
                         └────────────────────┬───────────────────┘
                                              ▼
                              embed + index (page, units on every chunk)
                                 ┌────────────┴────────────┐
                                 ▼                         ▼
                         ChromaDB (dense)          rank_bm25 (sparse)

                    QUERY (every request)
  question ──► hybrid retrieval ──► Cohere rerank ──► LLM ──► answer + sources
```

## Ingestion

`scripts/ingest.py` runs the stages below and rebuilds the index each time.

### 1. Read and clean (`pdf_loader.py`, `pdf_text.py`)

PyMuPDF reads each page. The extracted text is normalised: garbled or mojibake
characters are repaired, words hyphenated across line breaks are rejoined, letter-spaced
headings such as `G O V E R N M E N T` are collapsed to `GOVERNMENT`, and odd whitespace
is tidied.

### 2. Reading order (`pdf_layout.py`)

Text blocks on multi-column pages are reassembled in real reading order: the left column
first, then the right. Full-width titles stay where they are, so sentences and headings
read in sequence.

### 3. Running headers and footers (`pdf_text.py`)

The top and bottom lines of each page are compared across the document with digits
masked, so `Page 12` and `Page 7` match. Lines that recur on at least
`HEADER_FOOTER_MIN_RECURRENCE` pages are removed from the content. When a page's top line
is a section title (for example `Section IV: ...`), that section is kept as context for
the page.

### 4. Financial tables (`pdf_tables.py`)

- **Validate.** Detected grids are checked so that page layouts such as org charts are
  not treated as data tables.
- **Split.** Cells that stack several labels or values separated by newlines are split
  back into individual rows.
- **Flatten.** Each row becomes a self-contained key-value record, for example
  `U.S. Department of State | 2018: $270,596 | 2017: $310,971`. The record carries the
  table's descriptor, its units (such as "Dollars in thousands"), and its page, so a
  number always travels with what it means.

### 5. Prose (`pdf_chunker.py`, `chunker.py`)

Narrative text is split into overlapping windows (`CHUNK_SIZE` characters,
`CHUNK_OVERLAP` shared between neighbours). Breaks snap to paragraph boundaries when
possible, and each window keeps its section and page.

### 6. Indexing (`indexer.py`)

Every chunk, prose and table row alike, is:

- embedded (local MiniLM by default, or OpenAI embeddings) and stored in the ChromaDB
  collection `gpo_report`;
- added to a `rank_bm25` index built from the same text;
- recorded in a metadata sidecar with its text, page, units, section, and chunk type.

## Query path

```
POST /chat or /chat/stream
  └─ pipeline.run_pipeline(query, history)
       ├─ HybridRetriever.retrieve(query)
       ├─ Reranker.rerank(query, candidates, k)
       └─ Generator.generate(query, top-k chunks, history)
```

### Hybrid retrieval (`rag/retriever.py`)

Dense and sparse search cover each other's weak spots: embeddings match paraphrases,
while BM25 matches exact terms such as program names and line-item labels.

1. **Dense:** embed the query, take the top `TOP_K_DENSE` chunks from Chroma by cosine
   similarity.
2. **Sparse:** tokenise the query, take the top `TOP_K_BM25` chunks from BM25.
3. **Fuse:** min-max normalise each score list to [0, 1], then combine them as
   `alpha * dense + (1 - alpha) * sparse`. `HYBRID_ALPHA` is the single blend knob:
   `1.0` is pure dense, `0.0` is pure BM25, `0.5` is the default.

Fused candidates are looked up in the metadata sidecar to recover their full text, page,
units, and chunk type.

### Rerank (`rag/reranker.py`)

Retrieval casts a wide net; the reranker picks the best of it. The Cohere cross-encoder
scores each candidate against the query and the top `TOP_K_RERANK` chunks go forward to
the LLM. With `RERANKER_ENABLED=false`, the top chunks in fused order are used instead.

### Generate (`rag/generator.py`)

One generator interface has Gemini (default) and OpenAI implementations, chosen with
`LLM_PROVIDER`. The same prompt is used for both, so eval results compare across
providers. The prompt tells the model to answer using only the supplied chunks, to state
the units and page for every number, and to cite inline. Recent conversation history is
passed along for follow-up questions.

### Transport (`routers/chat.py`)

- `POST /chat` returns `{ answer, sources, latency_ms }` as JSON.
- `POST /chat/stream` returns Server-Sent Events: `token` events carrying answer
  fragments, then a `final` event with the answer, sources, and latency (`error` if
  something fails).

Each source carries its chunk id, title, a short snippet, its fused or rerank score,
page, units, and chunk type, which the UI shows in its sources panel.

## Data on disk (`backend/data/`)

Three files must exist before the server can handle requests:

| Path | Contents |
| --- | --- |
| `chroma/` | Chroma persistent vector store (collection `gpo_report`) |
| `bm25.pkl` | BM25 index pickle (`{bm25, ids}`) |
| `docs_meta.json` | chunk id → full chunk record, used during fusion |

The retriever, reranker, generator, and embedder are cached singletons loaded on the
first request. An idle manager clears them after a quiet period to free memory; they
reload on the next request.

## Evaluation

`eval/run_eval.py` runs the live pipeline over a verified gold Q&A set
(`eval/dataset.json`) and reports:

- **Ragas** metrics: faithfulness, answer relevancy, context precision, context recall.
- **Page-based retrieval hit-rate:** whether the retrieved chunks include a reference
  page for the question.

GitHub Actions runs `python -m eval.run_eval --check-thresholds` and fails the build if
any Ragas metric falls below its floor (faithfulness 0.70, answer relevancy 0.70,
context precision 0.55, context recall 0.55). Reports are written to
`backend/eval/reports/`.

## Design choices

- **One record per table row.** A number is only useful with its row label, column year,
  units, and page, so each row is stored as one self-contained chunk.
- **Hybrid search.** Financial line items and program names reward exact-term matching,
  while narrative questions reward semantic matching; blending both with one knob keeps
  tuning simple.
- **Retrieve wide, rerank narrow.** Hybrid search favours recall and the cross-encoder
  favours precision, so the LLM sees a small, relevant context.
- **Swappable providers.** LLM and embedding backends are chosen by environment variable
  behind one interface each; the same prompt keeps results comparable.
- **Cited answers.** Every source carries page and units, so each number in an answer can
  be traced back to the report.

## License

MIT
