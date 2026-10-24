# Plan: iMac PER PDF RAG Pipeline (v1)

**Spec:** `docs/superpowers/specs/2026-10-24-imac-pdf-rag-pipeline-design.md`
**Branch:** `IMAC-Report` (in-place transform of `backend/`; fresh from the Express blueprint)
**Execution:** subagent-driven-development — per task: implementer → reviewer → fix-loop; whole-branch review at the end.

## Global constraints (every task obeys)

- **Python**: `import pymupdf` (v1.28.2), not `fitz`. Chroma persistent, rank_bm25, sentence-transformers MiniLM (384-dim).
- **Pages are 1-based**, single-sourced in the loader/chunker — never recomputed downstream.
- **`source_path`** = PDF basename (`iMac_PER_Oct2024.pdf`), set at ingest time.
- **Reranker preserves every Candidate field** via `dataclasses.replace(c, score=...)` — never rebuild a Candidate by hand (GEP regression).
- **Header/footer strip excludes numeric-only templates** — never delete numeric body lines.
- **Column detection** by gutter/extents + band segmentation, not a fixed center gap.
- **Table titles**: short caption only; never title a table from a prose paragraph (>80 chars ⇒ no title); keep a column-descriptor sub-header as the title when present; never fabricate a row label.
- **Units travel with every figure**: inline in prose chunks; in `units` metadata for table rows.
- **Eval report output is ascii-only** (Windows cp1252 console).
- **Tests that open the PDF carry a skip-guard** (`pytest.importorskip("pymupdf")` + skip if the PDF is absent). `pytest.ini` sets `pythonpath = .`.
- `TOP_K_RERANK` default **10**. Straight pipeline only (no self-healing/HyDE/cache).
- Run tests from `backend/`. Don't commit `backend/data/` or `*.pdf` or `.superpowers/`.

## Tasks

### Task 1 — Config, dependencies, data paths (haiku)
- Edit `app/config.py` in place: `collection_name="imac_report"`; add `source_pdf_path` (default `../iMac_PER_Oct2024.pdf`); keep `chroma`/`bm25.pkl`/`docs_meta.json` data paths; set `top_k_rerank=10`; **remove** all self-healing / HyDE / semantic-cache settings.
- `requirements.txt`: ensure `pymupdf` present; keep existing RAG deps.
- `.env.example`: iMac-oriented, no self-healing/cache vars, `TOP_K_RERANK=10`, both LLM providers documented.
- **Test**: `get_settings()` loads; `collection_name == "imac_report"`; removed settings are gone.

### Task 2 — Strip self-healing + reranker field-preservation + pytest.ini (sonnet)
- `app/rag/pipeline.py`: reduce to `retrieve → rerank → generate`; drop self-healing/HyDE/cache/trace.
- `app/rag/reranker.py`: `_CohereReranker.rerank` uses `dataclasses.replace(c, score=float(r.relevance_score))`; passthrough when no key.
- Remove self-healing modules/trace emitters; simplify `/chat/stream` to token(s) then final.
- Add `pytest.ini` (`pythonpath = .`).
- **Test**: reranker preserves `page/units/chunk_type`; pipeline returns answer+sources with no trace.

### Task 3 — Text normalization (`pdf_text.py`, pure) (sonnet)
- `normalize_text(str)->str`: repair mojibake, replace non-breaking spaces, de-hyphenate line-wrap joins (digit-guarded — never join across digits), collapse inline whitespace while preserving paragraph breaks.
- `strip_running_headers(pages: list[str])->list[str]`: digit-masked recurrence detection, exclude numeric-only templates; also expose the detected running header so the loader can derive a section breadcrumb.
- **Test**: mojibake/nbsp repaired; `"foot-\nprint"`→`"footprint"` but `"2024-\n25"` preserved; the `iMac | Product Environmental Report N` header is detected/removable; a numeric body line is NOT removed.

### Task 4 — Span-aware extraction + superscript stripping (`pdf_spans.py`) (sonnet)
- `extract_blocks(page)->list[Block]`: read `page.get_text("dict")`; for each line compute the dominant (body) font size; **drop numeric-only spans whose size is meaningfully smaller** than the line body size (footnote markers like `9`, `5`, `18`), then join spans into clean word/line/block text. Guard real body numbers (same-size digits like `391`, `346`) from being dropped.
- `Block` = `(x0, y0, x1, y1, text)` — the shape `pdf_layout`/`pdf_tables` consume.
- **Test (real PDF, skip-guarded)**: on a page with footnote markers, `electricity9`/`chemistry5` do NOT appear (clean `electricity`/`chemistry` do); a body figure like `391` IS still present.

### Task 5 — Column reading-order (`pdf_layout.py`) (sonnet)
- `order_blocks(blocks, page_width)->list[Block]`: detect single vs two-column via gutter/extents; segment into horizontal bands (full-width headings vs column body); order top-band → left-column → right-column → next band. Reuse the proven GEP/GPO approach.
- **Test**: synthetic two-column blocks return in reading order; a full-width heading stays above the columns; single-column pages pass through unchanged.

### Task 6 — Strict table extraction (`pdf_tables.py`) (sonnet)
- `extract_tables(page, page_number)->list[TableRecord]`: run `find_tables()`, **validate strictly** — require ≥2 data columns, consistent column counts across rows, mostly-filled cells, numeric data present; **reject** 1×N fragments and the infographic-as-table (lots of `None`/empty). For survivors (the p11 power table), emit per-row key-value records: `title` (short caption / column-descriptor sub-header, prose-guarded), `units`, `page`, and `row_label -> {col: value}`. Return each table's bbox for subtraction.
- **Test (real PDF, skip-guarded)**: the p11 power-consumption table validates and yields per-row records with voltages as columns + a power unit; the p1 carbon-footprint infographic does NOT produce a table.

### Task 7 — PDF loader orchestration (`pdf_loader.py`) (sonnet)
- `load_pdf(path)->LoadedDoc`: per page → `extract_blocks` (Task 4) → `extract_tables` (Task 6) → subtract table bboxes from blocks → `order_blocks` (Task 5) → strip running header + derive section (Task 3) → `normalize_text` (Task 3). Produce ordered prose text per page (1-based `page`, `section`) + table records. No figures. `source_path` = basename.
- **Test (real PDF, skip-guarded)**: returns 12 pages; prose carries clean terms + inline units; table records present for p11; pages are 1-based; no header lines in prose.

### Task 8 — Chunk model + chunker (`pdf_chunker.py`) (sonnet)
- Extend `Chunk` (or new dataclass) with `page:int`, `section:str`, `chunk_type:str` (`prose`|`table_row`), `units:str|None`, `table_title:str|None`, `source_path:str`.
- Prose → sliding window (reuse blueprint window/overlap + paragraph-snap, no frontmatter), `section` breadcrumb (fallback `Page N`).
- Table rows → one chunk each, text prefixed `[Table: {title} | units: {units} | page {page}]` then `row_label: col=value; …`; carry `units`/`table_title`.
- **Test**: prose chunks respect window/overlap and keep page+section; a table row renders with its prefix + units; ids are stable/unique.

### Task 9 — Indexer + retriever metadata (sonnet)
- `indexer.py`: persist the new metadata (`page`, `section`, `chunk_type`, `units`, `table_title`, `source_path`) into Chroma + `docs_meta.json`; build BM25 over chunk text; keep `{bm25, ids}` pickle shape.
- `retriever.py`: carry the metadata through fusion onto `Candidate` (so rerank/generator/sources see page+units).
- **Test**: round-trip a tiny chunk set → Chroma + BM25 + docs_meta written; retrieve returns candidates with page/units/chunk_type populated.

### Task 10 — Generator prompt (sonnet)
- `generator.py`: iMac **product environmental report** system prompt — answer only from context, cite page + units, give exact figures with units, say when the report doesn't contain it. Keep Gemini (default) + OpenAI behind the Generator protocol, same template for both.
- **Test**: prompt builder includes page+units from sources; both providers constructible (mocked).

### Task 11 — Ingest CLI + build the index (sonnet)
- `scripts/ingest.py`: wire loader → chunker → indexer over `source_pdf_path`; log page/chunk/table counts; `--source` override.
- Run it to build `backend/data/` for the iMac report. Record chunk count.
- **Test**: dry-run wiring (mocked indexer) asserts loader→chunker→indexer order; real build produces non-empty Chroma + bm25.pkl + docs_meta.json.

### Task 12 — Eval harness + gold set (sonnet)
- Port `eval/run_eval.py` (Ragas, `--check-thresholds`, **ascii-safe** report, page-based `reference_pages`, thresholds unchanged). Export `OPENAI_API_KEY` from `.env` before running (Ragas reads `os.environ`).
- Author `eval/dataset.json`: ~12–15 **verified** items — carbon footprint (kg CO2e), power consumption (W) at 115V/230V, recycled content (%), packaging, plus definition/narrative items — each with the correct answer + `reference_pages` cross-checked against the PDF.
- Run the full eval; capture metrics + page hit-rate.
- **Test**: dataset loads + schema-valid; harness runs end-to-end on a 2-item smoke subset.

## Sequencing

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12. (3–6 are independent of each other after 2; 7 depends on 3–6; 8 on 7; 9 on 8; 10 parallel after 2; 11 on 9+10; 12 on 11.) Run independent tasks concurrently where the implementer pool allows.

## Done = 
All task tests green, index built, full Ragas eval run with metrics recorded, whole-branch review clean. (Frontend wiring + docs rewrite + push follow after owner reviews the backend — same as GEP/GPO.)
