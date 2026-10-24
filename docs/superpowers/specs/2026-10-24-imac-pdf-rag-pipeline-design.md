# Design: iMac PER PDF RAG Pipeline (v1)

**Date:** 2026-10-24
**Status:** Approved (strategy agreed by owner)
**Branch:** `IMAC-Report` (built fresh from the Express blueprint on `main`; independent of the GEP/GPO branches)

## Intent & why

Build a standalone RAG pipeline grounded in `iMac_PER_Oct2024.pdf` — Apple's **iMac Product
Environmental Report** (12 pages, digital text, macOS Quartz PDF). It must answer questions
about the product's environmental data — exact figures ("what is the total carbon footprint
of the iMac?", "sleep power consumption at 115V?") and narrative ("how does Apple reduce the
carbon footprint?", "what does 'carbon footprint' mean here?").

The existing Express/markdown backend is reused as the **blueprint** (architecture, hybrid
retrieval, reranker, generator). On `IMAC-Report`, `backend/` is transformed **in place**.
`main` keeps the Express app. Written fresh here (not merged from GEP/GPO), same proven shape.

## What makes this document different (drives the strategy)

Verified by inspection:
- **The data reads cleanly as linear text.** The environmental facts are label→value pairs:
  p9 extracts as "Carbon Footprint … iMac (four ports) 512GB … 391 kg CO2e … Total product
  footprint 346 kg CO2e … Life cycle product emissions (scope 3) 346 kg CO2e …". So a
  prose chunk captures the figure *with* its units and context.
- **`find_tables()` is mostly noise here.** It shatters the label→value facts into 1×2
  fragments and mis-reads the carbon-footprint *infographic* (p1) as a 10×4 grid full of
  `None`. Only the **power-consumption table** (p11: Mode × 100V/115V/230V) is a genuine grid.
- **Superscript footnote markers glue onto words.** Body text is ~11pt; footnote markers are
  5–7pt digits (`Low-carbon electricity9`, `chemistry5`, `ENERGY STAR.18`). Block-level text
  concatenates them into the word, polluting key terms.
- **Running header** `iMac | Product Environmental Report N` on every page.
- **Images/infographics** on several pages (p0, p3, p5, p7) are decorative; the numbers live
  in the text and the one real table.
- **Definitions (p8)** and **Endnotes (p11)** are useful narrative context.

## Goals

- Ingest the report into a dedicated index (Chroma dense + BM25 sparse).
- **Prose-first** ingestion: capture the environmental facts as clean text chunks that keep
  their page and units.
- **Strip superscript footnote markers** during extraction so key terms stay clean.
- Correct reading order on mixed one/two-column pages; strip the running header (keep section).
- Extract **only genuine grid tables** (the power-consumption table) into per-row records with
  units + page; leave fragmented/infographic layouts to the prose path.
- Answer exact-figure + narrative questions via new endpoints, citing page + units.
- Reuse the stack: Chroma+BM25 hybrid, Cohere rerank (passthrough without a key), Gemini
  (default)/OpenAI generator, local sentence-transformers embeddings.
- Measurable quality: Ragas harness + a **verified** iMac gold set, page-based hit-rate, CI
  thresholds unchanged (faithfulness 0.70 / answer_relevancy 0.70 / context_precision 0.55 /
  context_recall 0.55).

## Non-goals (v1)

- Figures/images (decorative; the data is in text + the one table).
- Self-healing / HyDE / semantic cache — straight path: retrieve → rerank → generate.
- OCR (digital text).
- The GEP and GPO reports (separate pipelines).
- Frontend — a later effort once the backend is validated.

## Anti-goals (failure even if it "works")

- A figure returned **without its units** (e.g. "346" with no "kg CO2e"). Every chunk must
  carry units inline; table rows carry them in metadata too.
- **Superscript footnote digits polluting terms** (`electricity9`, `chemistry5`) in chunks.
- The carbon-footprint **infographic emitted as a data table** (false-positive grid).
- Column text interleaved out of reading order; the running header polluting chunks.

## The "how" — decisions made

### Project layout — in place on `IMAC-Report`

Transform `backend/` in place (mirrors GEP/GPO, written fresh):
- `app/ingestion/`: add `pdf_text.py` (pure cleanup), `pdf_spans.py` (span-aware extraction +
  superscript stripping), `pdf_layout.py` (column order), `pdf_tables.py` (strict table
  extraction), `pdf_loader.py` (orchestration), `pdf_chunker.py` (prose + table_row chunks);
  retire `chunker.py` (markdown) + `loader.py`. `indexer.py` kept, `Chunk`/metadata extended.
- `app/config.py`: edit in place — `collection_name="imac_report"`, `source_pdf_path`, data
  paths; remove self-healing/cache settings; `top_k_rerank=10`.
- `app/rag/`: keep retriever/reranker/embeddings/generator (generator gets an iMac
  product-environmental prompt, units-aware). Strip self-healing from `pipeline.py`;
  **reranker preserves all Candidate fields** (`dataclasses.replace`).
- `main.py`, `routers/`: keep FastAPI shape; endpoints point at the iMac index.
- `scripts/ingest.py`: replace — ingest `iMac_PER_Oct2024.pdf`.
- `eval/`: keep & adapt the Ragas harness + an iMac gold set.

### Ingestion pipeline (per page)

1. **Span-aware extraction + superscript stripping** (`pdf_spans.py`): read page spans
   (`get_text("dict")`); drop numeric spans whose font size is notably smaller than the
   line's dominant body size (footnote markers), then assemble block-like text with clean
   words. Produces `Block(x0,y0,x1,y1,text)` objects (same shape the layout/table modules use).
2. **Detect & validate genuine tables** (`pdf_tables.py`): run `find_tables()`, keep only grids
   that pass strict validation (≥2 data columns, consistent column counts, mostly-filled,
   numeric content) — this rejects the 1×2 fragments and the infographic. Extract per-row
   key-value records with units + page.
3. **Subtract validated-table bboxes** from the block set before prose ordering.
4. **Resolve reading order** (`pdf_layout.py`): gutter/extents detection + band segmentation.
5. **Strip repeating header/footer** (`pdf_text.py`): digit-masked recurrence, excluding
   numeric-only templates; capture the running section as the page breadcrumb.
6. **Normalize** (`pdf_text.py`): repair mojibake, replace non-breaking spaces, de-hyphenate
   line breaks (digit-guarded), collapse inline whitespace while keeping paragraphs.

### Chunking

- **Prose** → sliding window (reuse the blueprint window + paragraph-snap, no frontmatter),
  `section` from the page breadcrumb (fallback `Page N`) + page; `chunk_type="prose"`.
- **Table rows** → one key-value chunk per row, prefixed with `[Table: {title} | units:
  {units} | page {page}]`; `chunk_type="table_row"`, `table_title`, `units`.
- No figure chunks.
- `page` is 1-based, single-sourced in loader/chunker. `source_path` = PDF basename at ingest.

### Reused from the blueprint

HybridRetriever (Chroma dense + BM25, min-max fused by `HYBRID_ALPHA`), `TOP_K_*` (rerank
default 10), Cohere rerank (passthrough without key; **preserve Candidate fields** on rerank),
Generator protocol (Gemini/OpenAI), local MiniLM embeddings, indexer (Chroma + BM25 +
docs_meta), API shape (`/health`, `/chat`, simplified `/chat/stream` = token then final).

### Evaluation

Port `eval/run_eval.py` + CI; page-based `reference_pages`; **ascii-safe report output**.
Author a **verified** iMac gold set (~12–15 items: environmental-figure lookups cross-checked
against the report — carbon footprint kg CO2e, power consumption W, recycled content %, etc. —
plus narrative/definition items). Thresholds unchanged.

## Lessons carried from GEP + GPO (baked in from the start)

- Reranker preserves `page/units/chunk_type` (`dataclasses.replace`).
- Header/footer strip excludes numeric-only templates (don't delete numeric body lines).
- Column detection by gutter/extents + band segmentation, not center-gap.
- Table titles: a short caption only; never title a table from a prose paragraph; keep a
  column-descriptor sub-header as the title when present.
- Never fabricate table row labels; drop or fall back.
- 1-based page numbering, single-sourced; `source_path` set at ingest.
- `TOP_K_RERANK=10`; ascii-only eval report output; tests opening the PDF carry a skip-guard;
  `pytest.ini` sets `pythonpath = .`.

## What's left to the builder

- Superscript detection threshold (how much smaller than body counts as a footnote marker),
  and guarding real body numbers (e.g. "391 kg CO2e") from being stripped — tune on real pages.
- Table validation thresholds (what disqualifies the 1×2 fragments / infographic).
- Column-gap / header-recurrence thresholds.

## Open questions for the owner

(To be filled from the builder-check pass before hand-off.)
