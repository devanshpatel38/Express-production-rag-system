# Design: GPO PDF RAG Pipeline (v1)

**Date:** 2026-10-23
**Status:** Draft for approval
**Branch:** `GPO-Report` (built fresh from the Express blueprint on `main`; independent of the GEP branch — owner decision)

## Intent & why

Build a standalone RAG pipeline grounded in `GPO-Anual-report.pdf` — the **U.S. Government
Publishing Office 2018 Annual Report** (82 pages, digital text, Adobe PDF Library). It must
answer **both** exact-figure questions (e.g. "What were GPO's total billings to the Dept. of
State in 2018?" — pulled from the financial-statement tables) and narrative questions (e.g.
"What were GPO's main priorities in 2018?" — from the management discussion and letters).

The existing Express/markdown backend on this branch is reused as the **blueprint** (architecture,
hybrid retrieval, reranker, generator). On `GPO-Report`, `backend/` is transformed **in place**
into this GPO pipeline. `main` keeps the Express app. This is a *separate* pipeline from GEP; the
code is written fresh here (not merged from `GEP-Report`), though the architecture is the same
proven shape.

## Goals

- Ingest `GPO-Anual-report.pdf` into a dedicated index (Chroma dense + BM25 sparse).
- Handle the document's verified layout challenges:
  - **Letter-spaced text** (`U . S . G O V …`) — collapse to real words.
  - **Multi-column pages** — correct reading order (left col then right).
  - **Financial-statement tables** with newline-packed cells — split into per-row key-value chunks.
  - **Running section-title headers/footers** — strip from body, keep as section breadcrumb.
- Answer exact-figure + narrative questions via new endpoints.
- Reuse the Express stack: Chroma+BM25 hybrid, Cohere rerank (passthrough without a key),
  Gemini/OpenAI generator, local sentence-transformers embeddings.
- Measurable quality: port the Ragas eval harness + a **verified** GPO gold Q&A set, page-based
  retrieval hit-rate, CI thresholds unchanged (faithfulness 0.70 / answer_relevancy 0.70 /
  context_precision 0.55 / context_recall 0.55).

## Non-goals (v1)

- **Figures / images.** The report has 0 caption-anchored figures and ~35 pages of *uncaptioned*
  photos/infographics. There's nothing to anchor on, and uncaptioned decorative images rarely hold
  queryable facts. v1 produces **no figure chunks** (prose + table rows only). Vision-describing
  uncaptioned images is a documented v2 option. (This removes any LLM-vision dependency at ingest.)
- Self-healing / HyDE / semantic cache — straight path: retrieve → rerank → generate.
- OCR (document is digital text).
- The GEP and iMac PDFs (separate pipelines).
- Frontend — a later effort once the backend is validated.
- Complex multi-statement reconciliation across financial tables (comparisons/aggregation across
  tables); v1 targets single-figure lookup + narrative.

## Anti-goals (failure even if it "works")

- A figure/billing number returned **without its units or period** (e.g. "270,596" with no
  "dollars in thousands, 2018"). Financial tables are dense with numbers — every table-derived
  chunk must carry the table's units caption and the column (year) header.
- **Letter-spaced garbage** in chunks (`G O V E R N M E N T`) — breaks embeddings and BM25.
- The **org-chart page** emitted as real data tables (false positives).
- Column text **interleaved out of reading order**.
- A standalone page number or running section header **polluting** prose chunks.

## Constraints & verified facts (from inspection)

- 82 pages, letter size, producer `Adobe PDF Library 15.0`.
- **Letter-spacing**: headers/titles render as spaced capitals (`U . S . G O V E R N M E N T …`).
- **Mixed columns**: many single-column (letters, MD&A), some 2-column (p41 16/8, p80 8/6).
- **Tables**:
  - `find_tables()` on the **org-chart page (p27)** returns **13 bogus tables** — must be rejected.
  - **Financial tables** (e.g. p80, "Notes to the Financial Statements") pack **multiple logical
    rows into a single grid cell**, newline-separated: one cell holds a stack of department names,
    the adjacent cell holds the matching stack of `"$ 270,596 33.3%\n78,283 9.6%\n…"`. Extraction
    must split these aligned newline stacks back into per-row records.
  - Header rows carry units captions like `(Dollars in thousands)` and year columns `2018` / `2017`.
- **Figures**: 0 `Figure N.N` captions; 35/82 pages carry uncaptioned image blocks.
- **Running headers**: section titles recur (`Section IV: Notes to the Financial Statements` ×21,
  `Section I: Management Discussion and Analysis (Unaudited)` ×15) plus the letter-spaced GPO banner
  on divider pages.

## The "how" — decisions made

### Project layout — in place on `GPO-Report`

Transform `backend/` in place (mirrors the GEP approach, written fresh):
- `app/ingestion/` — **replace** the markdown path:
  - `pdf_loader.py` (PyMuPDF extraction + table detect/validate + reading order + header strip +
    letter-spacing-aware cleanup),
  - `pdf_tables.py` (financial-table extraction: validate, reject org-chart false positives, split
    newline-packed cells into rows, attach units/year columns),
  - `pdf_chunker.py` (prose + table-row chunks — **no figure chunks**),
  - retire `chunker.py` (markdown) + `loader.py`.
  - `indexer.py` — keep, extend `Chunk`/metadata (page, chunk_type, units, table_title).
- `app/config.py` — edit in place: `collection_name="gpo_report"`, `source_pdf_path`, data paths;
  **remove** self-healing/cache settings.
- `app/rag/` — keep `retriever.py`, `reranker.py`, `embeddings.py`, `generator.py` (generator gets
  a GPO/government-report prompt with units-aware citations). Strip self-healing from `pipeline.py`.
- `app/main.py`, `routers/` — keep FastAPI shape; endpoints point at the GPO index.
- `scripts/ingest.py` — replace: ingest `GPO-Anual-report.pdf`.
- `eval/` — keep & adapt the Ragas harness + a GPO gold set.

### PDF library (my call)

**PyMuPDF** (`pymupdf`), same rationale as GEP (fast, reading order, `find_tables()`, coordinates).

### Ingestion pipeline (per page)

1. **Extract** text blocks + coordinates; skip pages with no text and no valid tables.
2. **Detect & validate tables first** (`find_tables()` → validation rejecting inconsistent /
   mostly-empty grids, i.e. the org-chart false positives).
3. **Subtract validated-table bounding boxes** from the text-block set before prose ordering.
4. **Resolve reading order** on remaining prose blocks (column detection: gutter/extents based).
5. **Strip repeating headers/footers** (digit-masked recurrence; excludes numeric-only templates),
   capturing recurring **section titles** as the page's section breadcrumb rather than body text.
6. **Normalize text**: collapse **letter-spacing** (`U . S . G O V` → `U.S. GOV…`), repair
   encoding, de-hyphenate line breaks (digit-guarded), collapse inline whitespace (keep paragraphs).

### Table handling — financial tables (the hard GPO part)

For each validated table:
- Identify the **units caption** (e.g. `(Dollars in thousands)`) and the **year/value column
  headers** (`2018`, `2017`, or `Billings % of Total`).
- **Split newline-packed cells:** when a label cell holds N newline-separated lines and the aligned
  value cell(s) hold N newline-separated entries, zip them into N logical rows
  (`label_i -> {col: value_i}`). Validate counts match; if they don't, fall back to emitting the raw
  cell text as one row rather than mis-aligning (never fabricate an alignment).
- Emit **one key-value chunk per logical row**, prefixed with a metadata header
  `[Table: {title} | units: {units} | page {page}]`, e.g.
  `U.S. Department of State | 2018: $ 270,596 (33.3%) | 2017: $ 310,971 (37.9%)`.
- `chunk_type="table_row"`, carry `table_title`, `units`, `page`.

### Chunking

- **Prose** → sliding window (reuse the blueprint window + paragraph-snap, no frontmatter),
  `section` from the captured section breadcrumb + page; `chunk_type="prose"`; `page` set.
- **Table rows** → as above.
- **No figure chunks** (v1 non-goal).
- `page` is **1-based** and single-sourced in the loader/chunker (as in GEP).
- `source_path` set to the PDF basename during ingest.

### Reused as-is from the blueprint

HybridRetriever (Chroma dense + BM25, min-max fusion by `HYBRID_ALPHA`), `TOP_K_*` knobs
(default `TOP_K_RERANK` raised to 10 — GEP learning for figure/row recall), Cohere rerank
(passthrough without key; **preserve all Candidate fields on rerank** — GEP bug learning), the
Generator protocol (Gemini/OpenAI), local MiniLM embeddings, the indexer (Chroma + BM25 + docs_meta
sidecar), API shape (`/health`, `/chat`, simplified `/chat/stream`).

### Evaluation

Port `eval/run_eval.py` + CI; page-based `reference_pages`; **ascii-safe report output** (GEP
Windows-console learning). Author a **verified** GPO gold set (~12–15 items: financial-figure
lookups cross-checked against the real tables, plus narrative items from the MD&A/letters).
Thresholds unchanged.

## Lessons carried from the GEP build (bake in from the start)

- Reranker must preserve `page/units/chunk_type` (use `dataclasses.replace`).
- Header/footer strip must exclude numeric-only templates (don't delete numeric body lines).
- Column detection by **gutter/extents**, not center-gap.
- Never fabricate table row labels; drop or fall back instead.
- 1-based page numbering, single-sourced; `source_path` set at ingest.
- `TOP_K_RERANK=10` default.
- Ascii-only console output in the eval report.
- Tests that open the PDF carry a skip-guard; `pytest.ini` sets `pythonpath = .`.

## What's left to the builder

- Column-gap / table-validation / letter-spacing thresholds — tune against sampled GPO pages.
- The newline-packed-cell split heuristic (count-matching, fallback) — tune against p80-class tables.
- Whether any additional financial tables need special handling.
- Final package naming and whether to carry self-healing features (no — v1 excludes them).

## Open questions for the owner

(To be filled from the builder-check pass before hand-off.)
