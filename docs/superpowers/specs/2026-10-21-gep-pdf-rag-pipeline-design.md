# Design: GEP PDF RAG Pipeline (v1)

**Date:** 2026-10-21
**Status:** Draft for approval
**Author:** Devansh (with Claude)

## Intent & why

The existing `backend/` is a RAG chatbot over the Express.js markdown docs. We want
a RAG pipeline grounded in a single PDF — `GEP-Jun-2026.pdf`, the World Bank
*Global Economic Prospects, June 2026* flagship report (200 pages). It must answer
**both**:

- **Exact-figure questions** — "What is the 2026 GDP growth forecast for
  Sub-Saharan Africa?" (pulled from the report's economic data tables), and
- **Narrative questions** — "What are the main risks to the global outlook?"
  (from the prose).

The Express backend is reused as the **blueprint** (architecture, hybrid
retrieval, reranker, generator). On a **dedicated branch**, the existing `backend/`
is transformed **in place** into this GEP pipeline — the Express-specific
ingestion/content is replaced, the architecture is kept. `main` keeps the Express
chatbot untouched; the GEP app lives only on the branch. The two apps are **not**
required to coexist or run side by side.

## Goals

- Ingest `GEP-Jun-2026.pdf` into a dedicated search index.
- Correctly handle the document's real layout challenges (verified by inspection):
  - **Multi-column pages** — read in proper order (left column fully, then right).
  - **Economic data tables** — reshaped so a single figure is retrievable.
  - **Narrative prose** — chunked with section context preserved.
- Answer exact-figure and narrative questions via a new endpoint set.
- Reuse the Express stack: Chroma dense + BM25 sparse hybrid retrieval, Cohere
  rerank, Gemini/OpenAI generator, local sentence-transformers embeddings.
- **Measurable quality bar (owner decision):** port the blueprint's Ragas eval
  harness (`eval/run_eval.py`) and CI gating (faithfulness/answer-relevancy/
  context-precision/context-recall floors) to this pipeline, backed by a
  hand-authored GEP gold Q&A set with **verified** exact figures and narrative
  answers. "Done" = clears the thresholds, not merely "runs."
- **Index all validated tables, including the statistical appendix** (owner
  decision). Each row chunk's table metadata (title/section/page/units) must be
  rich enough to keep near-identical appendix rows disambiguated under retrieval;
  near-duplicate-row drowning is a known risk to watch and tune.

## Non-goals (v1)

- The other two PDFs (`iMac_PER_Oct2024.pdf`, `GPO-Anual-report.pdf`). Each gets
  its **own** pipeline later; this version is tuned to the GEP report only.
- **Cross-table comparison / ranking** questions ("rank EMDE regions by 2027
  growth"). v1 targets *exact single figures* + narrative. Whole-table chunks
  that enable comparison are a documented v2 upgrade.
- A structured/queryable table store (CSV/SQLite + text-to-SQL). v1 is pure-RAG
  (tables become text chunks). This is the most likely v2 upgrade.
- **Full chart-to-data extraction** (recovering *unlabeled* plotted values as
  numbers, e.g. DePlot-style). Figures are handled by vision-LLM understanding of
  **labeled** values + captions/trends only, with explicit abstention on
  unlabeled values (owner decision). Scanned-page OCR is still out (the document
  is digital text).
- A general document-type router. Not needed for a single document.
- **Self-healing RAG / HyDE / semantic cache** — removed from v1, deferred to v2.
- Frontend work. Backend pipeline + API only. The Next.js frontend **will** need
  changes, but only **after** the backend is complete and working (owner decision);
  it is out of scope for this backend effort.

## Anti-goals (what makes this a failure even if it "works")

- Returning a figure **without its units / reference period** (e.g. "4.0" with no
  "percent, 2026 forecast"). A retrieved number orphaned from its table metadata
  is worse than no answer. Every table-derived chunk must carry its units and
  period context.
- Chunks polluted by **running headers/footers** (`CHAPTER 1 GLOBAL ECONOMIC
  PROSPECTS | JUNE 2026 45`) repeated on every page, degrading retrieval.
- **Garbled text** from the known encoding damage (see Constraints) silently
  flowing into the index.
- Column text **interleaved out of reading order** (right-column sentence spliced
  into the middle of a left-column paragraph).

## Constraints & verified facts (from inspection of the actual PDF)

- 200 pages, letter size (612×792). Producer: `GPL Ghostscript 9.06`.
- **Encoding damage:** extraction yields `�` where curly quotes, `©`, and similar
  special glyphs belong (Ghostscript glyph-mapping issue). Needs a normalization
  pass.
- **Mixed column counts:** some pages single-column (front matter, copyright),
  many 2-column (e.g. references on p66: 11 blocks left / 15 right), data pages
  mixed. Column handling must be **per-page adaptive**, not a fixed 2-column
  assumption.
- **Real data tables** exist (e.g. p100: forecast tables with year columns
  `2023 2024 2025e 2026f 2027f` and row labels like `EMDE SSA, GDP`). PyMuPDF
  `find_tables()` detects them but sometimes **splits one wide table into
  fragments** — fragments may need merging, and detections must be validated.
- **Blank / figure-only pages** exist (0 text blocks) — skip gracefully.
- **Running headers/footers** on content pages carry chapter + page number.

## The "how" — decisions made

### Project layout — in-place on a dedicated branch (owner decision)

**No new folder.** The work happens on the **`GEP-Report` branch**, where the
existing `backend/` app is **transformed in place** to
become the GEP pipeline, reusing the blueprint's architecture. `main` keeps the
Express chatbot untouched; the GEP app exists only on this branch. There is no
requirement to keep the two apps runnable side by side.

What changes vs. what stays, inside the existing `backend/`:

- `app/ingestion/` — **replace** the markdown path with the PDF path:
  - add `pdf_loader.py` (PyMuPDF extraction + table/figure detection + reading
    order + header-strip + encoding cleanup),
  - add `pdf_chunker.py` (prose + table-row + figure chunking),
  - retire/replace `chunker.py` (markdown) and `loader.py` (markdown walker).
  - `indexer.py` — **keep**, extend `Chunk`/metadata (page, chunk_type, units…).
- `app/config.py` — **edit in place**: GEP-appropriate `collection_name`, data
  paths, chunk knobs; **remove** the self-healing/HyDE/semantic-cache settings
  (deferred to v2, see below).
- `app/rag/` — **keep** `retriever.py`, `reranker.py`, `embeddings.py`,
  `generator.py` (generator gains vision-model use for figure ingestion and a
  units-aware prompt; retrieval/rerank reused as-is).
- `app/main.py`, `app/routers/` — **keep** the FastAPI shape; endpoints repoint at
  the GEP index. Whether paths/titles are renamed from "express" to "gep" is a
  builder detail.
- `scripts/ingest.py` — **replace**: ingest `GEP-Jun-2026.pdf` instead of walking
  a markdown directory.
- `eval/` — **keep & adapt** the Ragas harness + CI to the GEP gold set.
- `app/data/` (`chroma/`, `bm25.pkl`, `docs_meta.json`) — rebuilt from the PDF.
- Frontend — out of scope; may be repointed later.

Rationale: owner wants a single pipeline on this branch, not two coexisting apps.
Reusing the blueprint in place (rather than a parallel copy) avoids duplication and
keeps the diff reviewable.

### PDF parsing library (my call, owner may veto)

**PyMuPDF (`pymupdf`).** Fast, good multi-column reading-order support via text
blocks + coordinates, built-in `find_tables()`, exposes page numbers and block
bounding boxes (needed for header/footer stripping). Alternative considered:
`pdfplumber` (cleaner on ruled tables, slower, weaker on prose) — rejected for a
prose-heavy 200-page report. Already installed during inspection.

### Ingestion pipeline (per page)

1. **Extract** text blocks with coordinates via PyMuPDF. Skip pages with no text
   blocks (blank/figure pages).
2. **Detect & validate tables first:** run `find_tables()`, then **validate** each
   candidate (consistent column count across rows, mostly non-empty cells,
   numeric/short cells) to reject layout-driven false positives. Merge adjacent
   fragments of the same table where detectable.
3. **Subtract table regions from the prose stream** (builder-check call): remove
   the bounding boxes of validated tables from the text-block set *before* prose
   ordering, so a wide table's cells are never shredded by the column splitter and
   its numbers are never indexed twice (once garbled as prose, once as clean KV
   rows). This directly protects two anti-goals. Only the remaining prose blocks
   flow to the next step.
4. **Resolve reading order** (prose blocks only): detect column count per page by
   clustering text blocks on their x-position (gap in x-centers ⇒ multi-column).
   Emit left column top-to-bottom, then right column — never interleaved.
   Single-column pages pass through in natural order.
5. **Strip repeating headers/footers:** detect text lines that recur at the same
   vertical position across many pages (adaptive; no hardcoded strings) and drop
   them. Captured chapter/section context is retained as metadata, not body text.
6. **Normalize encoding:** repair the known `�` artifacts (map to the correct
   punctuation/symbols where determinable), collapse abnormal whitespace, fix
   hyphenation at line breaks.
7. **Figure understanding (vision-LLM, labeled-only):** identify figure regions
   (embedded image blocks and/or caption-anchored regions like "Figure 1.2"),
   render each region to an image, and send it to the stack's vision model
   (Gemini/GPT) to produce a **figure chunk**: the caption, a short description of
   what it shows / the trend, and any values that are **literally labeled** in the
   figure. The prompt must instruct the model to **abstain** on values that are
   not printed ("not stated in the figure") — never infer a number from a plotted
   position. This protects the faithfulness gate.

### Chunking strategy

**Prose chunks** — reuse the Express sliding-window idea (`chunk_size` /
`chunk_overlap` from config, paragraph-boundary snapping) **but**:
- Source is cleaned, reading-ordered page text, not markdown.
- **Drop** the markdown frontmatter stripping (not applicable to PDF).
- Breadcrumbs come from detected **section/heading context + chapter**, carried
  into each chunk's `section`/`title`, plus the **page number**.

**Table chunks (per-row key-value — v1 primary)** — each validated table row
becomes one self-contained chunk:
- Flattened as `Region: Sub-Saharan Africa | 2023: 3.0 | 2024: 3.8 | 2025e: 4.1
  | 2026f: 4.0 | 2027f: 4.4` (header-labeled key-value pairs).
- Prefixed with a **table metadata header** repeated on every row chunk: table
  title/caption, **units** (e.g. "percent, annual"), chapter/section, page, and
  any units caveats / footnotes.
- This makes a single figure directly retrievable *with* its context, satisfying
  exact-figure questions and the anti-goal on units.

**Figure chunks (vision-LLM, labeled-only)** — one chunk per figure region:
caption + description/trend + any literally-labeled values, with `chunk_type =
"figure"` and the page number. Abstains on unlabeled values by construction.

**Deferred to v2:** a whole-table chunk (full table rendered as markdown with the
same header) to enable comparison/ranking questions.

### Chunk metadata schema

The blueprint `Chunk` dataclass has fixed fields (`source_path`, `title`,
`section`, `text`, `char_start`, `char_end`). Extend it (or add a metadata dict)
with: `page` (int), `chunk_type` (`"prose"` | `"table_row"` | `"figure"`), and for
table rows `table_title`, `units`. The indexer's Chroma `metadatas` and the `docs_meta.json`
sidecar must carry these so the generator can cite page + units.

**Expose page + units as structured response fields (builder-check call).** The
blueprint `Source` schema carries only `source_path/title/snippet/score`. Extend
the GEP response contract's source objects with `page` and (for table rows)
`units`, rather than only baking them into the answer prose. Rationale: the
units/period anti-goal is load-bearing, and the design leaves open a later wiring
of the Next.js UI to these endpoints — structured citation fields are cheap now
and expensive to retrofit. The generator prompt still instructs it to state units
inline too, as a backstop.

### Reused as-is from the blueprint

- **Retrieval:** `HybridRetriever` (Chroma dense + BM25 sparse, min-max fused by
  `HYBRID_ALPHA`), the `TOP_K_*` knobs, Cohere rerank.
- **Generation:** `Generator` protocol with Gemini/OpenAI implementations, same
  prompt-template approach.
- **Embeddings:** local `all-MiniLM-L6-v2` by default (swappable to OpenAI).
- **Indexer mechanics:** Chroma + BM25 pickle + `docs_meta.json` sidecar,
  wipe-and-rebuild on reingest.
- **API shape:** `/health` and a chat endpoint, mirrored with GEP-specific
  config (own `collection_name`, own `data/` paths, own CORS).

**Self-healing / HyDE / semantic-cache are deferred to v2 (owner decision).** The
blueprint's closed-loop features (adaptive routing, HyDE, retrieval grading,
faithfulness self-healing loop, semantic cache) are **removed** from v1: drop their
settings from `config.py`, and keep the pipeline the straight path
retrieve → rerank → generate. They return in a later version.

### Evaluation (owner decision: full Ragas, CI-gated)

- Port the blueprint's `eval/run_eval.py` + `eval.yml` CI workflow to the GEP
  pipeline, keeping the same four Ragas metrics and threshold floors
  (faithfulness 0.70, answer-relevancy 0.70, context-precision 0.55,
  context-recall 0.55) unless tuning shows they need adjusting for this corpus.
- Author a **GEP gold Q&A dataset** (`eval/dataset.json` equivalent) with
  **verified** answers: exact-figure questions (answers cross-checked against the
  actual report tables), narrative questions, and at least some figure/label
  questions. Verifying the figures is real manual work and is on the critical path
  to a trustworthy faithfulness score.
- CI fails the build on any metric regression, mirroring the Express app.

## What's left to the builder

- Final package/app name and whether endpoints live on a new port or path prefix.
- Exact column-detection thresholds (x-gap) and header/footer-recurrence
  thresholds — tune against sampled pages.
- Table validation heuristics (what disqualifies a false-positive table) and
  fragment-merge rules — tune against the p100-style forecast tables.
- The precise `�`-repair mapping (determine the intended glyphs from context).
- Whether to tune `chunk_size`/`chunk_overlap` away from the Express defaults
  (700/120) for this report's prose density.
- Whether to carry over the self-healing/HyDE/cache features in v1.
- Test fixtures: a few representative pages (a 2-column prose page, the p100 table
  page, a blank page) to assert reading order, table KV output, and header
  stripping.

## Resolved after builder-check (owner decisions)

- **Acceptance bar:** full Ragas eval harness + CI gating + verified GEP gold set.
- **Chart/figure content:** in scope via **vision-LLM, labeled-only** (abstain on
  unlabeled plotted values). Full chart-to-data extraction is a non-goal.
- **Table scope:** index **all validated tables, including the statistical
  appendix**; rely on rich per-row metadata to fight near-duplicate retrieval.
- **Builder calls folded in:** tables are subtracted from the prose stream before
  column-ordering; page + units are exposed as structured response fields.

## Calls I made for you (verify while reading)

- PDF library = PyMuPDF. In-place transform of `backend/` on the `GEP-Report`
  branch (no new folder; `main` keeps the Express app).
- Prose chunk uses the blueprint's sliding-window + breadcrumb approach, minus the
  markdown frontmatter logic.
- Table/figure handling order within the per-page pipeline (tables → subtract →
  prose → headers → encoding → figures).
- Response schema extended with `page` and `units`.
