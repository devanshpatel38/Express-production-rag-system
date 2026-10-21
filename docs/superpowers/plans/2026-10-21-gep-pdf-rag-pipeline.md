# GEP PDF RAG Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the existing Express-docs RAG backend, in place on the `GEP-Report` branch, into a RAG pipeline over `GEP-Jun-2026.pdf` that answers exact-figure, narrative, and labeled-figure questions.

**Architecture:** Keep the blueprint's architecture (hybrid Chroma+BM25 retrieval → Cohere rerank → Gemini/OpenAI generate). Replace the markdown ingestion path with a PDF path (PyMuPDF extraction, per-page table/figure detection, column reading-order, header/footer strip, encoding cleanup) that emits three chunk kinds: prose windows, table-row key-value chunks, and figure chunks. Strip the self-healing/HyDE/cache layer down to the straight path. Port the Ragas eval harness to a GEP gold set.

**Tech Stack:** Python 3.11, FastAPI, PyMuPDF, ChromaDB, rank-bm25, sentence-transformers (local MiniLM), Cohere rerank, Gemini/OpenAI (text + vision), Ragas.

**Spec:** `docs/superpowers/specs/2026-10-21-gep-pdf-rag-pipeline-design.md`

## Global Constraints

- Work on branch `GEP-Report`, transforming `backend/` **in place**. No new top-level app folder. `main` keeps the Express app.
- All backend commands run from `backend/`; paths like `./data/` are relative to it. The source PDF is at repo root: `../GEP-Jun-2026.pdf` relative to `backend/`.
- Python 3.11. Pin every new dependency to an exact version in `backend/requirements.txt`.
- Reuse blueprint values verbatim unless a task changes them: `top_k_dense=15`, `top_k_bm25=15`, `top_k_rerank=5`, `hybrid_alpha=0.5`, local embeddings `all-MiniLM-L6-v2` (384-dim), Chroma `hnsw:space=cosine`, `llm_provider` default `gemini` (`gemini-1.5-flash`), rerank model `rerank-english-v3.0`.
- Ragas thresholds stay: faithfulness 0.70, answer_relevancy 0.70, context_precision 0.55, context_recall 0.55.
- Chroma metadata values must be `str|int|float|bool` (never `None`) — use `""` for absent `units`/`table_title`.
- v1 excludes self-healing, HyDE, semantic cache, cross-table comparison chunks, OCR of scanned pages, full chart-to-data extraction, and the other two PDFs.
- Commit after each task. End every commit message with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Tests use `pytest`. Add `pytest` to requirements if not present. Unit tests must not hit live LLM/rerank APIs — mock them. One integration test (Task 12) runs the real ingest on sampled pages.

## Review Focus

Inputs the spec implies but that no single task's happy-path test exercises; each gets a test in the owning task:

- **Blank / image-only page (0 text blocks, e.g. p1, p198):** ingestion must skip it without crashing and produce no empty chunks. → Task 8.
- **False-positive table (layout mis-detected as a grid):** validation must reject a candidate whose rows have inconsistent column counts / mostly-empty cells, so it is not emitted as table rows. → Task 6.
- **Table row whose label column is empty / unmatched:** row-label association must degrade gracefully (fall back to table title + row index) rather than emit `Region: None`. → Task 6.
- **Figure with no printed data labels:** vision description must abstain ("values not stated in the figure"), never invent a number. → Task 7.
- **Question whose answer is absent from the report:** generator must say it cannot answer from the context, not hallucinate. → Task 11.
- **`�` encoding artifact in source text:** must be normalized before it reaches the index. → Task 3.

---

## Task 1: Dependencies + GEP configuration

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `get_settings()` returning a `Settings` with GEP fields: `collection_name="gep_report"`, `source_pdf_path: str = "../GEP-Jun-2026.pdf"`, `vision_enabled: bool = True`, `header_footer_min_recurrence: int = 10`, `figure_caption_regex: str = r"(?im)^\s*figure\s+\d+\.\d+"`. Self-healing/cache fields removed.

- [ ] **Step 1: Add dependencies.** In `requirements.txt` add `pymupdf==1.24.14` and `pytest==8.3.3`. Remove `markdown-it-py==3.0.0` and `beautifulsoup4==4.12.3` (markdown-only; retired in Task 9). Pin `pymupdf` to the actually-resolved version if different (`python -c "import pymupdf; print(pymupdf.__version__)"`).
- [ ] **Step 2: Write the failing test** `test_config.py::test_gep_settings`:
```python
def test_gep_settings():
    s = get_settings.__wrapped__()  # bypass lru_cache
    assert s.collection_name == "gep_report"
    assert s.source_pdf_path.endswith("GEP-Jun-2026.pdf")
    assert not hasattr(s, "self_healing_enabled")
    assert not hasattr(s, "semantic_cache_enabled")
```
- [ ] **Step 3: Run test, verify it fails** (`pytest backend/tests/test_config.py -v`). Expected: FAIL.
- [ ] **Step 4: Edit `config.py`:** change `collection_name` to `"gep_report"` and the three `data/` paths may stay (`./data/...`). Add the new GEP fields above. **Delete** the entire `--- Self-healing RAG ---` and `--- Semantic cache ---` sections (all fields from `self_healing_enabled` through `semantic_cache_size`). Update `app_name` to `"gep-report-rag"`.
- [ ] **Step 5: Run test, verify pass.**
- [ ] **Step 6: Commit** (`feat: GEP config + deps, drop self-healing/cache settings`).

---

## Task 2: Strip self-healing → straight pipeline, update schemas/health/chat

**Files:**
- Delete: `backend/app/rag/router.py`, `cache.py`, `grader.py`, `query_rewriter.py`, `verifier.py`
- Modify: `backend/app/rag/pipeline.py`, `app/models/schemas.py`, `app/routers/chat.py`, `app/routers/health.py`
- Test: `backend/tests/test_pipeline_naive.py`

**Interfaces:**
- Produces:
  - `Source(BaseModel)`: `chunk_id: str`, `source_path: str`, `title: str`, `snippet: str`, `score: float`, `page: int | None = None`, `units: str | None = None`, `chunk_type: str = "prose"`.
  - `ChatResponse(BaseModel)`: `answer: str`, `sources: list[Source]`, `latency_ms: int`.
  - `HealthResponse(BaseModel)`: `status: Literal["ok","degraded"]`, `indexed_chunks: int`, `llm_provider: str`, `reranker_enabled: bool`.
  - `ChatRequest(BaseModel)`: `query`, `history`, `top_k`, `use_reranker` (drop `use_self_healing`, `use_hyde`).
  - `run_pipeline(query: str, history: list[ChatMessage] | None = None, top_k: int | None = None, use_reranker: bool | None = None) -> PipelineResult` where `PipelineResult` has `answer: str`, `sources: list[Source]`, `latency_ms: int`, `pre_rerank: list[Candidate]`, `post_rerank: list[Candidate]`.
- Consumes: `get_retriever()`, `get_reranker()`, `get_generator()` (unchanged).

- [ ] **Step 1: Write failing test** `test_pipeline_naive.py::test_run_pipeline_straight_path` — monkeypatch `get_retriever`/`get_reranker`/`get_generator` with fakes returning 3 canned `Candidate`s and a fixed answer; assert `run_pipeline("q").answer == "fixed"`, `len(result.post_rerank) <= top_k_rerank`, and `result.sources[0].page` is carried through. Also assert `import app.rag.cache` raises `ModuleNotFoundError`.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Delete** the five self-healing modules listed above.
- [ ] **Step 4: Rewrite `pipeline.py`** to keep only the naive path: `run_pipeline` does `get_retriever().retrieve(query)` → if `get_reranker().enabled` then `rerank(query, candidates, target_k)` else `candidates[:target_k]` → `get_generator().generate(query, kept, history)` → build `PipelineResult`. `target_k = top_k or s.top_k_rerank`. Keep `_snippet` and a `_sources_from(candidates)` that now also sets `page`, `units`, `chunk_type` from each `Candidate` (Task 10 adds those fields). Remove `stream_self_healing`, `_run_self_healing`, `_retrieve_grade_filter`, `HealingEvent`/`trace` usage, and all `get_cache/get_grader/get_rewriter/get_router/get_verifier` imports.
- [ ] **Step 5: Edit `schemas.py`** to the shapes in Interfaces: extend `Source`, slim `ChatResponse`, slim `HealthResponse`, slim `ChatRequest`. Delete `EventStage` and `HealingEvent`.
- [ ] **Step 6: Edit `chat.py`:** `/chat` calls `run_pipeline(req.query, req.history, req.top_k, req.use_reranker)` and maps `PipelineResult` → `ChatResponse`. **Simplify `/chat/stream`** to: emit `token` events from `get_generator().stream(...)` over the reranked candidates, then one `final` event `{answer, sources, latency_ms}`. Drop the healing-trace replay and `event` stages. Keep `record_request()` and SSE headers.
- [ ] **Step 7: Edit `health.py`:** drop `self_healing_enabled` from the response; keep chunk count via the bm25 pickle.
- [ ] **Step 8: Run test, verify pass. Commit** (`refactor: strip self-healing to straight retrieve→rerank→generate`).

---

## Task 3: Text normalization

**Files:**
- Create: `backend/app/ingestion/pdf_text.py`
- Test: `backend/tests/test_pdf_text.py`

**Interfaces:**
- Produces: `normalize_text(s: str) -> str` — repairs known `�`/mojibake, collapses runs of whitespace, de-hyphenates words split across line breaks (`inter-\nvention` → `intervention`), and collapses letter-spaced runs (`U . S .` → `U.S.`, optional for GEP).

- [ ] **Step 1: Write failing tests** `test_pdf_text.py`:
```python
def test_dehyphenate_linebreak():
    assert normalize_text("inter-\nvention") == "intervention"
def test_collapse_whitespace():
    assert normalize_text("a   b\n\n c") == "a b\n\nc"  # paragraph breaks preserved, inline runs collapsed
def test_repair_replacement_char():
    # the Ghostscript artifact for a curly quote becomes a straight quote
    assert "�" not in normalize_text("Intervening �against� the Fed")
```
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement `normalize_text`.** Map `�` and common mojibake to best-guess ASCII/punctuation; preserve `\n\n` paragraph boundaries while collapsing inline whitespace; join hyphen-linebreak splits. Keep it a pure function.
- [ ] **Step 4: Run, verify pass. Commit** (`feat: PDF text normalization`).

---

## Task 4: Repeating header/footer detection & strip

**Files:**
- Modify: `backend/app/ingestion/pdf_text.py`
- Test: `backend/tests/test_headers.py`

**Interfaces:**
- Produces:
  - `collect_repeating_lines(pages_top_bottom: list[tuple[str, str]], min_recurrence: int) -> set[str]` — input is per-page `(top_line, bottom_line)`; returns the normalized line templates (digits masked to `#`) that recur at least `min_recurrence` times.
  - `strip_repeating(text: str, repeating: set[str]) -> str` — removes lines whose digit-masked form is in `repeating`.

- [ ] **Step 1: Write failing test** `test_headers.py::test_detects_and_strips_running_header`: build 20 synthetic pages whose top line is `f"CHAPTER {i%3} \nGLOBAL ECONOMIC PROSPECTS | JUNE 2026 \n{40+i}"`; assert the masked template `"CHAPTER # \nGLOBAL ECONOMIC PROSPECTS | JUNE #### \n##"` is in `collect_repeating_lines(..., min_recurrence=10)`, and that `strip_repeating` removes it from a page body while leaving real prose.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** both functions. Digit-mask = replace each `[0-9]` run... (replace each digit char with `#`). Count masked templates across pages; return those ≥ threshold. `strip_repeating` drops matching lines.
- [ ] **Step 4: Run, verify pass. Commit** (`feat: adaptive running header/footer strip`).

---

## Task 5: Column reading-order resolution

**Files:**
- Create: `backend/app/ingestion/pdf_layout.py`
- Test: `backend/tests/test_layout.py`

**Interfaces:**
- Produces: `order_blocks(blocks: list[Block], page_width: float) -> list[Block]` where `Block` is a lightweight dataclass `{x0,y0,x1,y1,text}`. Detects 1 vs 2 columns by gap in block x-centers around `page_width/2`; emits left column top-to-bottom, then right column. Single-column pages return natural top-to-bottom order.

- [ ] **Step 1: Write failing tests** `test_layout.py`:
```python
def test_two_column_reading_order():
    # left blocks x-center ~150, right ~460; interleaved y
    blocks = [B(400,60,560,80,"R1"), B(60,60,250,80,"L1"),
              B(400,100,560,120,"R2"), B(60,100,250,120,"L2")]
    assert [b.text for b in order_blocks(blocks, 612)] == ["L1","L2","R1","R2"]
def test_single_column_passthrough():
    blocks = [B(60,100,550,120,"P2"), B(60,60,550,80,"P1")]
    assert [b.text for b in order_blocks(blocks, 612)] == ["P1","P2"]
```
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement `order_blocks`.** Two-column test: cluster x-centers; if a clear left/right split exists (two clusters separated across mid), sort each side by `y0`, left then right; else sort all by `y0`. Threshold tunable.
- [ ] **Step 4: Run, verify pass. Commit** (`feat: multi-column reading-order resolution`).

---

## Task 6: Table extraction + row-label association + validation

**Files:**
- Create: `backend/app/ingestion/pdf_tables.py`
- Test: `backend/tests/test_tables.py` (uses the real PDF, page 100)

**Interfaces:**
- Produces:
  - `@dataclass TableData`: `page: int`, `title: str`, `units: str`, `columns: list[str]`, `rows: list[tuple[str, dict[str, str]]]` (each = `(row_label, {column: value})`), `bbox: tuple[float,float,float,float]`.
  - `extract_tables(page: "pymupdf.Page", page_text_blocks: list[Block]) -> list[TableData]`.
  - `is_valid_table(raw_rows: list[list], min_rows: int = 2) -> bool`.

**Key algorithm — row-label association (the spec's flagged risk):** `page.find_tables()` returns the numeric grid but drops the left label column (rows come back like `[None, None, '4.1', ...]` and the header is `['2023','2024','2025e','2026f','2027f','2028f']`). For each grid row, take its y-band (`row bbox` or the table bbox split into `row_count` bands) and find the text block(s) immediately **left of** `table.bbox.x0` overlapping that y-band — that text is the `row_label`. If none found, fall back to `f"{title} row {i}"`.

- [ ] **Step 1: Write failing tests** `test_tables.py` against `../GEP-Jun-2026.pdf` page 100:
```python
def test_page100_table_has_year_columns():
    tds = extract_tables(page100, blocks100)
    cols = tds[0].columns
    assert "2026f" in cols and "2027f" in cols
def test_page100_rows_have_labels_not_none():
    tds = extract_tables(page100, blocks100)
    # every emitted row has a non-empty label and at least one numeric value
    for td in tds:
        for label, cells in td.rows:
            assert label and label.strip()
            assert any(v and v.strip() for v in cells.values())
def test_rejects_inconsistent_grid():
    assert is_valid_table([["a","b"],["c"]]) is False
```
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement.** `extract_tables`: run `page.find_tables()`, drop candidates failing `is_valid_table` (consistent column count across rows, ≥ `min_rows`, majority cells non-empty), merge horizontally-adjacent fragments sharing a y-band, associate row labels per the algorithm above, infer `units`/`title` from the nearest caption text above the table bbox (regex for `Table`/`percent`/`U.S. dollars` cues; else `""`). `is_valid_table` as asserted.
- [ ] **Step 4: Run, verify pass. Commit** (`feat: table extraction with row-label association + validation`).

---

## Task 7: Figure detection + region render + vision description

**Files:**
- Create: `backend/app/ingestion/pdf_figures.py`, `backend/app/rag/vision.py`
- Test: `backend/tests/test_figures.py`

**Interfaces:**
- Produces:
  - `@dataclass FigureContent`: `page: int`, `caption: str`, `description: str`.
  - `detect_figure_regions(page, caption_regex: str) -> list[tuple[str, tuple[float,float,float,float]]]` — returns `(caption, clip_bbox)` per figure; `clip_bbox` spans the column from the caption upward to the previous caption/heading (generous crop is acceptable).
  - `describe_figures(page, regions, describer) -> list[FigureContent]` — renders each `clip_bbox` to PNG via `page.get_pixmap(clip=rect, matrix=pymupdf.Matrix(2,2))` and calls the describer.
  - In `vision.py`: `get_vision_describer() -> VisionDescriber` (`@lru_cache`); `VisionDescriber.describe(self, png_bytes: bytes, caption: str) -> str`. Gemini/OpenAI backends chosen by `s.llm_provider`, reusing `s.gemini_model`/`s.openai_model` (both vision-capable). **Prompt instructs: describe what the figure shows and report ONLY values printed as labels; if a value is not printed, say "not stated in the figure" — never infer from position.**

- [ ] **Step 1: Write failing tests** `test_figures.py`:
```python
def test_detects_figure_captions_on_sample_page():
    regions = detect_figure_regions(sample_fig_page, CAPTION_REGEX)
    assert len(regions) >= 1 and regions[0][0].lower().startswith("figure")
def test_describe_uses_describer_and_abstains(monkeypatch):
    fake = FakeDescriber(ret="Line chart of GDP growth; values not stated in the figure.")
    out = describe_figures(sample_fig_page, [("Figure 1.1",(60,100,300,300))], fake)
    assert out[0].caption == "Figure 1.1"
    assert "not stated" in out[0].description
```
(Pick `sample_fig_page` by scanning the PDF for the caption regex in a fixture helper.)
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** detection (regex over page text lines → caption bbox → clip upward), rendering, and the two vision backends. Unit tests mock the describer; no live API in tests.
- [ ] **Step 4: Run, verify pass. Commit** (`feat: figure detection + vision description (labeled-only, abstaining)`).

---

## Task 8: PDF loader orchestration

**Files:**
- Create: `backend/app/ingestion/pdf_loader.py`
- Delete: `backend/app/ingestion/loader.py`
- Test: `backend/tests/test_pdf_loader.py` (real PDF, sampled pages)

**Interfaces:**
- Produces:
  - `@dataclass PageContent`: `page: int`, `prose_text: str`, `tables: list[TableData]`, `figures: list[FigureContent]`.
  - `load_pdf(pdf_path: str, describe_figures_fn=None) -> list[PageContent]` — two passes: (1) collect repeating header/footer templates across all pages; (2) per page: detect+validate tables (Task 6), detect figures (Task 7), **subtract table & figure bboxes** from the text-block set, order remaining prose blocks (Task 5), strip repeating lines (Task 4), normalize (Task 3). Pages with no text blocks and no tables/figures are skipped. `describe_figures_fn` defaults to `get_vision_describer()` but is injectable for tests (and to disable vision via `s.vision_enabled`).

- [ ] **Step 1: Write failing tests** `test_pdf_loader.py` against `../GEP-Jun-2026.pdf`:
```python
def test_blank_page_skipped():
    pages = load_pdf(PDF, describe_figures_fn=noop_describer)
    assert all(p.prose_text or p.tables or p.figures for p in pages)  # no empty PageContent
def test_running_header_absent_from_prose():
    pages = load_pdf(PDF, describe_figures_fn=noop_describer)
    joined = " ".join(p.prose_text for p in pages)
    assert "GLOBAL ECONOMIC PROSPECTS | JUNE" not in joined
def test_table_page_yields_tabledata():
    pages = {p.page: p for p in load_pdf(PDF, describe_figures_fn=noop_describer)}
    assert pages[100].tables and pages[100].tables[0].columns
```
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement `load_pdf`** per the two-pass description; inject `noop_describer` in tests to keep them offline/fast.
- [ ] **Step 4: Run, verify pass. Commit** (`feat: PDF loader orchestration (tables→subtract→prose→strip→normalize)`).

---

## Task 9: Chunk model + PDF chunker

**Files:**
- Modify: `backend/app/ingestion/chunker.py` (extend `Chunk`; retire `chunk_markdown`)
- Create: `backend/app/ingestion/pdf_chunker.py`
- Test: `backend/tests/test_pdf_chunker.py`

**Interfaces:**
- Produces:
  - Extended `@dataclass Chunk` with existing fields plus `page: int = 0`, `chunk_type: str = "prose"`, `table_title: str = ""`, `units: str = ""`. `to_dict()` includes them.
  - `chunk_pages(pages: list[PageContent], chunk_size: int, chunk_overlap: int) -> list[Chunk]`:
    - **prose** → sliding window (reuse the blueprint's window + paragraph-snap logic, **no frontmatter stripping**); `section`/`title` from current chapter context + page; `chunk_type="prose"`, `page` set.
    - **table rows** → one `Chunk` per `(label, cells)`: `text = f"{title} — {label} | " + " | ".join(f"{col}: {val}" for col,val in cells.items())`, prefixed with a metadata header line (`[Table: {title} | units: {units} | page {page}]`); `chunk_type="table_row"`, `table_title`, `units`, `page` set.
    - **figures** → one `Chunk`: `text = f"[Figure: {caption} | page {page}] {description}"`; `chunk_type="figure"`, `page` set.

- [ ] **Step 1: Write failing tests** `test_pdf_chunker.py`:
```python
def test_table_row_chunk_is_keyvalue_with_units():
    td = TableData(page=100,title="EMDE growth",units="percent",columns=["2026f"],
                   rows=[("Sub-Saharan Africa",{"2026f":"4.0"})],bbox=(0,0,0,0))
    chunks = chunk_pages([PageContent(100,"",[td],[])], 700, 120)
    row = [c for c in chunks if c.chunk_type=="table_row"][0]
    assert "Sub-Saharan Africa" in row.text and "2026f: 4.0" in row.text
    assert row.units == "percent" and row.page == 100
def test_prose_windowing_no_frontmatter_logic():
    long = "para one.\n\n" + "x "*800
    chunks = chunk_pages([PageContent(5, long, [], [])], 700, 120)
    assert len(chunks) >= 2 and all(c.chunk_type=="prose" for c in chunks)
def test_figure_chunk_carries_caption():
    pc = PageContent(7,"",[],[FigureContent(7,"Figure 1.1","desc")])
    c = [c for c in chunk_pages([pc],700,120) if c.chunk_type=="figure"][0]
    assert "Figure 1.1" in c.text and c.page == 7
```
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement.** Extend `Chunk`; delete `chunk_markdown` and `_strip_frontmatter` (and `HEADING_RE` if unused); port the windowing loop into `pdf_chunker` operating on `prose_text`.
- [ ] **Step 4: Run, verify pass. Commit** (`feat: PDF chunker — prose/table-row/figure chunks`).

---

## Task 10: Indexer + retriever metadata plumbing

**Files:**
- Modify: `backend/app/ingestion/indexer.py`, `backend/app/rag/retriever.py`
- Test: `backend/tests/test_indexer_meta.py`

**Interfaces:**
- Produces:
  - `indexer.build_indices(chunks)` writes `page`, `chunk_type`, `table_title`, `units` into Chroma `metadatas` (coercing `None`→`""`) and into the `docs_meta.json` records.
  - Extended `@dataclass Candidate` with `page: int | None = None`, `units: str = ""`, `chunk_type: str = "prose"`; `HybridRetriever` populates them from `docs_meta` when building candidates.
- Consumes: `Chunk` (Task 9).

- [ ] **Step 1: Write failing test** `test_indexer_meta.py::test_metadata_roundtrip` — build indices from 3 hand-made `Chunk`s (one `table_row` with `units="percent"`, `page=100`) into a tmp `data/` dir (monkeypatch settings paths), then `get_retriever().retrieve("...")` and assert a returned `Candidate` exposes `page==100` and `units=="percent"`. Assert no Chroma metadata value is `None`.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** metadata carry-through in both files.
- [ ] **Step 4: Run, verify pass. Commit** (`feat: carry page/units/chunk_type through index + retrieval`).

---

## Task 11: GEP generator prompt + units-aware citations

**Files:**
- Modify: `backend/app/rag/generator.py`
- Test: `backend/tests/test_generator_prompt.py`

**Interfaces:**
- Produces: new `SYSTEM_PROMPT` (World Bank GEP economic report; answer only from context; **state the units and reference period for every figure; cite inline as `[#n]`; if the context lacks the answer, say so plainly — never guess a number, especially from figures**). `_format_context` prefixes each block with page + units when present: `[#1] {section} (p{page}{, units})`.

- [ ] **Step 1: Write failing tests** `test_generator_prompt.py`:
```python
def test_context_block_shows_page_and_units():
    c = Candidate(chunk_id="x",text="4.0",source_path="GEP-Jun-2026.pdf",
                  title="t",section="EMDE growth",score=1.0,page=100,units="percent",chunk_type="table_row")
    out = _format_context([c])
    assert "p100" in out and "percent" in out
def test_system_prompt_forbids_guessing():
    assert "never" in SYSTEM_PROMPT.lower() and "context" in SYSTEM_PROMPT.lower()
```
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** the new prompt and `_format_context` (guard for `page is None`). Leave `generate`/`stream` wiring otherwise unchanged.
- [ ] **Step 4: Run, verify pass. Commit** (`feat: GEP generator prompt with units-aware citations`).

---

## Task 12: Ingest CLI + end-to-end index build (integration)

**Files:**
- Modify: `backend/scripts/ingest.py`
- Test: `backend/tests/test_ingest_e2e.py` (integration; sampled pages)

**Interfaces:**
- Produces: `python -m scripts.ingest --source ../GEP-Jun-2026.pdf [--max-pages N] [--no-vision]` — `load_pdf` → `chunk_pages` → `build_indices`; prints chunk counts by `chunk_type`. `--max-pages` limits pages (for the fast integration test); `--no-vision` injects the noop describer.

- [ ] **Step 1: Write failing integration test** `test_ingest_e2e.py::test_build_small_index` — run the ingest programmatically with `max_pages=~12` (include page 100) and `--no-vision` into a tmp `data/`; assert `docs_meta.json` exists, contains ≥1 `table_row` chunk with `units`, and `get_retriever().retrieve("Sub-Saharan Africa GDP growth 2026")` returns a candidate from page 100. Mark with `@pytest.mark.integration`.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Rewrite `ingest.py`** for the PDF path (replace the markdown walk). Keep the wipe-and-rebuild via `build_indices`.
- [ ] **Step 4: Run the test, verify pass.**
- [ ] **Step 5: Full build (manual step, not a test):** from `backend/`, run `python -m scripts.ingest --source ../GEP-Jun-2026.pdf` to build the real index (this makes the vision calls for ~54 figure pages). Record the printed chunk counts in the commit body.
- [ ] **Step 6: Commit** (`feat: PDF ingest CLI + full GEP index build`).

---

## Task 13: Ragas eval harness + GEP gold dataset

**Files:**
- Modify: `backend/eval/run_eval.py`, `backend/eval/dataset.json`
- Modify: `.github/workflows/eval.yml` (repoint if needed)
- Test: `backend/tests/test_eval_smoke.py`

**Interfaces:**
- Produces:
  - `dataset.json` with GEP items: `{"id","question","ground_truth","reference_pages":[int,...]}`. ~12–15 items spanning exact-figure (answers **verified against the report**), narrative, and labeled-figure questions.
  - `_retrieval_hit_rate` compares `reference_pages` against retrieved candidates' `page` (not markdown paths). `_run_pipeline_collect` sets `_retrieved_pages` from `post_rerank`. THRESHOLDS unchanged.

- [ ] **Step 1: Write failing test** `test_eval_smoke.py::test_dataset_and_hitrate_shape` — load `dataset.json`, assert every item has `reference_pages` as a non-empty `list[int]`; call `_retrieval_hit_rate` on a hand-made row with overlapping pages and assert `1.0`.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Author the gold dataset** (verify each figure against the actual report pages) and adapt `run_eval.py` page-based hit-rate + collection. Keep `time.sleep` between items for Ragas rate limits.
- [ ] **Step 4: Run test, verify pass.**
- [ ] **Step 5: Full eval (manual):** with the real index built (Task 12), run `python -m eval.run_eval --check-thresholds`; confirm it exits 0 (or record which metric is below floor to tune). Repoint `eval.yml` to this pipeline.
- [ ] **Step 6: Commit** (`feat: GEP Ragas eval harness + verified gold dataset`).

---

## Self-Review notes

- **Spec coverage:** reading order (T5), tables→subtract→prose ordering (T8), header strip (T4), encoding (T3), table row-KV + units (T6/T9), figures labeled-only (T7), page+units structured fields (T2/T10/T11), all-validated-tables incl. appendix (T6/T8/T12 via full build), Ragas CI (T13), self-healing removal (T1/T2), in-place on `GEP-Report` (Global Constraints). Comparison/ranking + other PDFs are explicit non-goals.
- **Near-duplicate appendix rows drowning retrieval** (spec risk) is not unit-testable cheaply; it surfaces in Task 13's hit-rate and is a tuning item (metadata-in-text already mitigates). Called out here rather than given a synthetic test.
- **Type consistency:** `Candidate`(+page,units,chunk_type), `Chunk`(+page,chunk_type,table_title,units), `Source`(+page,units,chunk_type), `TableData`, `PageContent`, `FigureContent` names are used identically across T6–T12.
