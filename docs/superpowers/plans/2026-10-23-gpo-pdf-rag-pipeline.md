# GPO PDF RAG Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Transform the Express-docs backend, in place on `GPO-Report`, into a RAG pipeline over `GPO-Anual-report.pdf` (U.S. GPO 2018 Annual Report) that answers exact-figure (financial) and narrative questions.

**Architecture:** Keep the blueprint architecture (hybrid Chroma+BM25 → Cohere rerank → Gemini/OpenAI generate). Replace markdown ingestion with a PDF path: PyMuPDF extraction, letter-spacing-aware cleanup, column reading-order, table detect/validate (reject org-chart false positives) + financial-table newline-packed-cell splitting, producing prose + table-row chunks (no figures). Strip self-healing to the straight path. Port the Ragas eval to a GPO gold set.

**Tech Stack:** Python 3.11, FastAPI, PyMuPDF, ChromaDB, rank-bm25, sentence-transformers (local MiniLM), Cohere rerank, Gemini/OpenAI, Ragas.

**Spec:** `docs/superpowers/specs/2026-10-23-gpo-pdf-rag-pipeline-design.md`

## Global Constraints

- Work on branch `GPO-Report`, transforming `backend/` in place. `main` keeps the Express app.
- All backend commands run from `backend/`. Source PDF at repo root: `../GPO-Anual-report.pdf`.
- Python 3.11; pin new deps exactly in `backend/requirements.txt` (`pymupdf==1.28.2`, `pytest==8.3.3`).
- Reuse blueprint values: `top_k_dense=15`, `top_k_bm25=15`, `hybrid_alpha=0.5`, local `all-MiniLM-L6-v2` (384-dim), Chroma `hnsw:space=cosine`, provider default `gemini`. **Set `top_k_rerank=10`** (GEP learning).
- Ragas thresholds unchanged: faithfulness 0.70, answer_relevancy 0.70, context_precision 0.55, context_recall 0.55.
- Chroma metadata values must be `str|int|float|bool`, never `None` (coerce `None`→`""`, page→int).
- `page` is 1-based, single-sourced in loader/chunker. `source_path` = PDF basename, set at ingest.
- **No figure chunks** in v1.
- **Lessons baked in from GEP (do these from the start, not as fixes):**
  - Reranker must preserve ALL Candidate fields (use `dataclasses.replace`, overwrite only score).
  - Header/footer strip must exclude numeric-only templates.
  - Column detection by gutter/extents (+ band segmentation), not center-gap.
  - Never fabricate table row labels — drop or fall back.
  - Eval report output must be ascii-only (Windows cp1252 console).
  - Tests opening the PDF carry `pytest.mark.skipif(not os.path.exists(PDF), ...)`; `pytest.ini` sets `pythonpath = .`.
- Commit after each task; end every message with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Tests use `pytest`; unit tests mock LLM/rerank APIs. One integration test (Task 11) runs real ingest on sampled pages (offline, fake embedder).

## Review Focus

- **Letter-spaced text** (`U . S . G O V`) reaching a chunk un-collapsed → Task 3.
- **Org-chart page (p27)** emitted as data tables → Task 6 validation.
- **Mismatched newline-packed cell counts** (labels N, values M≠N) → must fall back, never mis-zip → Task 6.
- **Numeric body line** stripped as a header → Task 4.
- **Question whose answer isn't in the report** → generator abstains → Task 10.
- **Blank page / no-text page** → skipped, no empty chunk → Task 7.

---

## Task 1: Dependencies + GPO configuration

**Files:** Modify `backend/requirements.txt`, `backend/app/config.py`; Test `backend/tests/test_config.py`.

**Interfaces — Produces:** `get_settings()` with `collection_name="gpo_report"`, `source_pdf_path="../GPO-Anual-report.pdf"`, `header_footer_min_recurrence: int = 8`. Self-healing/cache fields removed. `top_k_rerank=10`.

- [ ] Add `pymupdf==1.28.2`, `pytest==8.3.3`; remove `markdown-it-py`/`beautifulsoup4` if unused (grep first).
- [ ] Failing test `test_gpo_settings`: `collection_name=="gpo_report"`, `source_pdf_path` ends with `GPO-Anual-report.pdf`, `top_k_rerank==10`, no `self_healing_enabled`/`semantic_cache_enabled` attrs (use `get_settings.__wrapped__()`).
- [ ] Run → fail; edit config (set collection/paths/top_k_rerank, add fields, delete self-healing + semantic-cache sections, `app_name="gpo-report-rag"`); run → pass; commit.

## Task 2: Strip self-healing → straight pipeline (+ reranker field preservation), schemas/health/chat

**Files:** Delete `app/rag/{router,cache,grader,query_rewriter,verifier}.py`; Modify `app/rag/pipeline.py`, `app/rag/reranker.py`, `app/models/schemas.py`, `app/routers/chat.py`, `app/routers/health.py`; Test `backend/tests/test_pipeline_naive.py`.

**Interfaces — Produces:**
- `Source(BaseModel)`: `chunk_id, source_path, title, snippet, score, page: int|None=None, units: str|None=None, chunk_type: str="prose"`.
- `ChatResponse(BaseModel)`: `answer, sources, latency_ms`. `HealthResponse`: `status, indexed_chunks, llm_provider, reranker_enabled`. `ChatRequest`: `query, history, top_k, use_reranker`.
- `run_pipeline(query, history=None, top_k=None, use_reranker=None) -> PipelineResult(answer, sources, latency_ms, pre_rerank, post_rerank)`.
- **Reranker:** `_CohereReranker.rerank` must build results via `dataclasses.replace(candidate, score=...)` (preserve page/units/chunk_type).

- [ ] Failing test: straight-path `run_pipeline` with fake retriever/reranker/generator carries a fake Candidate's `page` through to `sources[0].page`; `import app.rag.cache` raises `ModuleNotFoundError`; AND a reranker test: `_CohereReranker.rerank` (fake client) preserves `page/units/chunk_type` and overwrites score.
- [ ] Delete the 5 modules; rewrite `pipeline.py` naive path (retrieve → rerank-if-enabled-else-slice → generate; `_sources_from` reads `getattr` defensively); fix `reranker.py` with `dataclasses.replace`; slim schemas (drop `EventStage`/`HealingEvent`); `/chat` maps result→ChatResponse; `/chat/stream` emits token then final `{answer,sources,latency_ms}`; `health.py` drops self_healing. Verify `python -c "import app.main"`. Run → pass; commit.

## Task 3: Text normalization (letter-spacing collapse central)

**Files:** Create `backend/app/ingestion/pdf_text.py`, `backend/tests/test_pdf_text.py`.

**Interfaces — Produces:** `normalize_text(s: str) -> str` — **collapses letter-spacing** (`"U . S . G O V"` → `"U.S. GOV"`; `"A N N U A L"` → `"ANNUAL"`), repairs encoding/mojibake, de-hyphenates line breaks (digit-guarded: don't join when a digit borders the break), collapses inline whitespace while preserving `\n\n` paragraphs.

- [ ] Failing tests:
  - `normalize_text("A N N U A L  R E P O R T") == "ANNUAL REPORT"`
  - `normalize_text("U . S . G O V E R N M E N T") == "U.S. GOVERNMENT"` (dotted initialism preserved, words joined)
  - `normalize_text("inter-\nvention") == "intervention"`; `normalize_text("2018-\n2017")` keeps the numbers separate
  - `normalize_text("a   b\n\n c") == "a b\n\nc"`; a normal sentence with real single spaces is unchanged
- [ ] Run → fail; implement (letter-spacing detector: runs of single-char tokens separated by single spaces → join, keeping `.`-initialisms readable); run → pass; commit.

**Builder note:** the letter-spacing collapse must NOT mangle ordinary prose (real words with normal spaces). Detect spaced-letter runs (≥3 consecutive single-character alpha tokens) and collapse only those.

## Task 4: Repeating header/footer strip + section-breadcrumb capture

**Files:** Modify `backend/app/ingestion/pdf_text.py`; Test `backend/tests/test_headers.py`.

**Interfaces — Produces:**
- `collect_repeating_lines(pages_top_bottom: list[tuple[str,str]], min_recurrence: int) -> set[str]` (digit-masked templates recurring ≥ threshold; **exclude numeric-only templates**).
- `strip_repeating(text: str, repeating: set[str]) -> str`.
- `section_for(top_line: str) -> str | None` — if a top line looks like a GPO section title (`"Section IV: Notes to the Financial Statements"`), return it (used as breadcrumb).

- [ ] Failing tests: a running `"Section IV: …"` top line recurring 20× is detected and stripped from a body while real prose survives; a standalone numeric line (`"26"`) and a 4-digit year (`"2018"`) both survive; `section_for("Section I: Management Discussion and Analysis")` returns it, `section_for("The GPO printed …")` returns None.
- [ ] Run → fail; implement; run → pass; commit.

## Task 5: Column reading-order (gutter/extents + band segmentation)

**Files:** Create `backend/app/ingestion/pdf_layout.py`, `backend/tests/test_layout.py`.

**Interfaces — Produces:** `@dataclass Block{x0,y0,x1,y1,text}`; `order_blocks(blocks, page_width) -> list[Block]`. Two-column only when non-spanning blocks split left/right with a real gutter (`max(left.x1) < min(right.x0)`); full-width blocks (crossing mid) segment the page into y-bands, each ordered left-then-right. Single-column → sort by y0.

- [ ] Failing tests: two-column interleaved-y → `["L1","L2","R1","R2"]`; single-column unsorted → natural y order; a centered title + full-width body + short left line → natural y order (not mis-split); a full-width title atop two columns → title first, then left col, then right col.
- [ ] Run → fail; implement; run → pass; commit.

## Task 6: Table extraction — validate + split newline-packed cells (the hard GPO part)

**Files:** Create `backend/app/ingestion/pdf_tables.py`, `backend/tests/test_tables.py` (real PDF, p80 + p27).

**Interfaces — Produces:**
- `@dataclass TableData{page:int, title:str, units:str, columns:list[str], rows:list[tuple[str, dict[str,str]]], bbox}`.
- `extract_tables(page, page_text_blocks: list[Block]) -> list[TableData]`.
- `is_valid_table(raw_rows: list[list], min_rows: int = 2) -> bool`.

**Key algorithm — newline-packed-cell split (the spec's flagged risk):** GPO financial tables (p80) pack multiple logical rows into single grid cells, newline-separated — a label cell holds N lines (`"U.S. Department of State\nU.S. Congress\n…"`) and the aligned value cell holds N lines (`"$ 270,596 33.3%\n78,283 9.6%\n…"`). For such a table: for each row whose cells contain `\n`, split each cell on `\n`; if the label column and the value column(s) yield the **same** count N, zip into N logical rows; **if counts differ, do NOT mis-align** — emit the raw cell text as a single row (fallback). Infer `units` from a caption cell/line like `(Dollars in thousands)`; `columns` from the year/label header row (`2018`, `2017`, `Billings % of Total`).

- [ ] Failing tests (real `../GPO-Anual-report.pdf`):
  - `is_valid_table` rejects the org-chart page: `len(extract_tables(doc[27], blocks27)) == 0` (the 13 bogus grids are all rejected).
  - p80 financial table: at least one emitted row has label `"U.S. Department of State"` with a `2018` value containing `270,596` and a `2017` value containing `310,971`; every emitted row has a non-empty label and ≥1 non-empty value.
  - a synthetic mismatched-count packed cell (labels=3, values=2) falls back to a single raw row rather than mis-zipping.
  - `is_valid_table([["a","b"],["c"]]) is False`.
- [ ] Run → fail; implement (find_tables → validate → caption/units + columns → packed-cell split with count-match + fallback → never fabricate); run → pass; commit.

## Task 7: PDF loader orchestration

**Files:** Create `backend/app/ingestion/pdf_loader.py`; delete `backend/app/ingestion/loader.py`; Test `backend/tests/test_pdf_loader.py` (real PDF).

**Interfaces — Produces:** `@dataclass PageContent{page:int, prose_text:str, tables:list[TableData]}`; `load_pdf(pdf_path: str) -> list[PageContent]`. Two passes: (1) collect repeating header/footer templates across all pages; (2) per page: detect+validate tables → subtract table bboxes from blocks → order prose (Task 5) → strip repeating + capture section breadcrumb (Task 4) → normalize (Task 3). `PageContent.page = pno+1`. Skip pages with no prose and no tables. Optional `max_pages` kwarg for fast tests.

- [ ] Failing tests (real PDF, adjust to 1-based pages): no empty PageContent (blank pages skipped); the letter-spaced GPO banner does NOT appear spaced in any `prose_text` (`"G O V E R N M E N T" not in joined`); the financial-table page yields a PageContent with non-empty `.tables`.
- [ ] Run → fail; implement; run → pass; commit.

## Task 8: Chunk model + PDF chunker

**Files:** Modify `backend/app/ingestion/chunker.py` (extend `Chunk`, retire `chunk_markdown`); Create `backend/app/ingestion/pdf_chunker.py`, `backend/tests/test_pdf_chunker.py`.

**Interfaces — Produces:** `Chunk` + `page:int=0, chunk_type:str="prose", table_title:str="", units:str=""` (to_dict includes them). `chunk_pages(pages: list[PageContent], chunk_size, chunk_overlap) -> list[Chunk]`:
- prose → sliding window (reuse window + paragraph-snap, no frontmatter), `chunk_type="prose"`, page + section from PageContent.
- table rows → one chunk per `(label, cells)`: `text = f"{title} — {label} | " + " | ".join(f"{col}: {val}")` prefixed with `[Table: {title} | units: {units} | page {page}]`; `chunk_type="table_row"`, `table_title`, `units`.
- Every Chunk.page from `PageContent.page` (1-based, single-sourced).

- [ ] Failing tests: a table row chunk is key-value with units (e.g. "U.S. Department of State" and "2018: $ 270,596" in text, units set, page from PageContent); prose windowing yields multiple prose chunks, no frontmatter logic; page comes from PageContent not TableData. Verify `python -c "import app.ingestion.indexer"`.
- [ ] Run → fail; implement; run → pass; commit.

## Task 9: Indexer + retriever metadata plumbing

**Files:** Modify `backend/app/ingestion/indexer.py`, `backend/app/rag/retriever.py`; Test `backend/tests/test_indexer_meta.py`.

**Interfaces — Produces:** indexer writes `page, chunk_type, table_title, units` into Chroma metadatas (None→"") and docs_meta. `Candidate` + `page:int|None=None, units:str="", chunk_type:str="prose"`, populated from docs_meta.

- [ ] Failing roundtrip test (fake embedder, tmp data dir): build from 3 Chunks (one table_row, units set, page=80) → retrieve → Candidate exposes `page==80`/`units`; no Chroma metadata value is `None`.
- [ ] Run → fail; implement; run → pass; commit.

## Task 10: GPO generator prompt + units-aware citations

**Files:** Modify `backend/app/rag/generator.py`; Test `backend/tests/test_generator_prompt.py`.

**Interfaces — Produces:** new `SYSTEM_PROMPT` (assistant answers about the U.S. GPO 2018 Annual Report using ONLY context; states units + reporting period/year for every figure; cites `[#n]`; says so plainly if not in context; never guesses a number). `_format_context` prefixes blocks with page + units: `[#1] {section} (p{page}, {units})` (guard None page / empty units).

- [ ] Failing tests: `_format_context([Candidate(..., page=80, units="dollars in thousands")])` contains "p80" and "dollars in thousands"; `SYSTEM_PROMPT.lower()` contains "never" and "context". Run → fail; implement; run (full suite) → pass; commit.

## Task 11: Ingest CLI + end-to-end build (integration)

**Files:** Modify `backend/scripts/ingest.py`; Test `backend/tests/test_ingest_e2e.py` (integration, offline).

**Interfaces — Produces:** `python -m scripts.ingest --source ../GPO-Anual-report.pdf [--max-pages N]` → `load_pdf` → `chunk_pages` → set `source_path`=basename → `build_indices`; print chunk counts by type.

- [ ] Failing integration test (`@pytest.mark.integration`, skip-guard): run ingest with `max_pages` covering p80 (1-based 81) + `--no-vision` n/a (no figures), fake embedder, tmp data dir; assert docs_meta has a table_row chunk with units and `source_path=="GPO-Anual-report.pdf"`, and `HybridRetriever().retrieve("Department of State billings 2018")` returns a candidate from the financial-table page.
- [ ] Run → fail; rewrite ingest; run → pass. Manual (record counts in commit): full build `python -m scripts.ingest --source ../GPO-Anual-report.pdf`. Commit.

## Task 12: Ragas eval + verified GPO gold dataset

**Files:** Modify `backend/eval/run_eval.py`, `backend/eval/dataset.json`, `.github/workflows/eval.yml`; Test `backend/tests/test_eval_smoke.py`.

**Interfaces — Produces:** `dataset.json` GPO items `{id, question, ground_truth, reference_pages:[int]}` (~12–15: financial-figure lookups **verified** against the real tables + narrative items from MD&A/letters). `_retrieval_hit_rate` page-based; `_run_pipeline_collect` sets `_retrieved_pages` from post_rerank. THRESHOLDS unchanged. **Ascii-only report output.**

- [ ] Failing smoke test: every dataset item has non-empty `reference_pages: list[int]`; `_retrieval_hit_rate` returns 1.0 on overlap, 0.0 on none. Run → fail; adapt harness (page-based, ascii-safe), author verified dataset (derive figures from real extracted tables), repoint `eval.yml`; run → pass; commit. Live `run_eval --check-thresholds` is a manual step (needs API key).

## Self-Review notes

- Spec coverage: letter-spacing (T3), org-chart rejection + packed-cell split (T6), section breadcrumb (T4), columns (T5), table-row+units chunks (T6/T8), page+units structured fields (T2/T9/T10), no figures (T8), Ragas (T12), self-healing removal + reranker-preserve + ascii-eval + numeric-strip + gutter-columns (baked into Global Constraints/tasks). Figures and cross-table comparison are non-goals.
- Type consistency: `Block`, `TableData`, `PageContent`, `Chunk`(+fields), `Candidate`(+fields), `Source`(+fields) used identically across T5–T11.
