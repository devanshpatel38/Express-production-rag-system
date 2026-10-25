# Architecture

The system answers questions about Apple's iMac Product Environmental Report. It has two
parts: an **ingestion pipeline** that turns the PDF into a search index (run once), and a
**request pipeline** that answers each question (retrieve, rerank, generate).

## Request lifecycle

```
POST /chat  or  POST /chat/stream
  └─ retrieve_and_rerank(query)
       ├─ HybridRetriever.retrieve(query)
       │    ├─ dense:  embed(query) -> Chroma top-15 (cosine similarity)
       │    ├─ sparse: tokenise -> BM25 top-15
       │    └─ fuse:   min-max normalise both, weighted sum (HYBRID_ALPHA)
       └─ Reranker.rerank(query, candidates, k)   <- Cohere, or passthrough
  └─ Generator.generate / stream(query, top chunks, history)
       └─ answer + sources (page, units, chunk type)
```

### 1. Hybrid retrieval

Two searches run on every question:

- **Dense.** The question becomes a 384-number vector with a local sentence-transformers
  MiniLM model. ChromaDB returns the closest chunks.
- **Sparse.** BM25 matches the exact words in the question. This catches precise terms and
  numbers that vectors can blur.

The two score lists are each rescaled to 0-1 (min-max), then blended:
`alpha * dense + (1 - alpha) * bm25`. `HYBRID_ALPHA` is the only knob: 0 is pure keyword,
1 is pure vector, 0.5 is the default. A sidecar file, `docs_meta.json`, maps each chunk id
to its full record so fused results come back with their text and metadata.

### 2. Reranking

A Cohere cross-encoder reads the question and each candidate together and re-scores them,
which is more precise than comparing vectors. The best `TOP_K_RERANK` chunks go on. If there
is no Cohere key, or reranking is switched off, the fused order is used as-is.

### 3. Generation

The generator builds a prompt from the kept chunks and the chat history and asks the model
to answer only from that context. Gemini and OpenAI sit behind one `Generator` interface and
share one prompt, so results are comparable across providers. The answer cites the page and
the units of each figure.

`/chat` returns the whole answer as JSON. `/chat/stream` sends Server-Sent Events: `token`
events while the answer is written, then one `final` event with the answer, sources and
latency. Each source has its page, units and chunk type.

## Ingestion pipeline

```
iMac_PER_Oct2024.pdf
  └─ pdf_loader.load_pdf
       per page:
         pdf_spans   extract text blocks (drop superscript footnote markers)
         pdf_tables  find genuine tables
         (blocks inside tables are removed from the prose)
         pdf_layout  put blocks in reading order
       once for the document:
         pdf_text    remove the running header
         pdf_text    normalise each page
  └─ pdf_chunker.chunk_document   prose windows + table-row chunks
  └─ indexer.build_indices        Chroma + bm25.pkl + docs_meta.json
```

| Module | What it does |
| --- | --- |
| `pdf_spans.py` | Reads text span by span. Numeric-only spans much smaller than the body text are footnote markers and are dropped, so "electricity9" becomes "electricity". Small chemical subscripts (CO2e) and real figures ("391 kg CO2e") are kept. |
| `pdf_text.py` | Repairs garbled characters, turns non-breaking spaces into spaces, rejoins words split by a line-end hyphen (never across digits), and collapses stray whitespace while keeping paragraphs. Detects the repeating "iMac \| Product Environmental Report N" header, which is removed. |
| `pdf_layout.py` | Finds the column gutter from the blocks' own positions. A block that crosses the gutter splits the page into bands; inside a band the left column is read before the right. |
| `pdf_tables.py` | Accepts only strictly validated grids. PyMuPDF's table finder is used as an anchor for the header, and rows are rebuilt from word positions aligned to the header columns. In this report the one real table is the power-consumption table (modes by 100V / 115V / 230V). |
| `pdf_loader.py` | Runs the steps above and produces, per page, the prose, the tables and the section name (the running section becomes the page's breadcrumb). |
| `pdf_chunker.py` | Cuts prose with a sliding window (`CHUNK_SIZE` 700, `CHUNK_OVERLAP` 120) and turns each table row into its own key-value chunk with its units. |
| `indexer.py` | Embeds the chunks into ChromaDB, builds the BM25 index, and writes the sidecar record file. |

Each chunk carries a 1-based page number, section, chunk type (`prose` or `table_row`),
units, table title and source file. The built index holds 50 chunks over 12 pages.

## Data on disk (`backend/data/`)

- `chroma/` - the persistent vector store
- `bm25.pkl` - the BM25 index (`{bm25, ids}`)
- `docs_meta.json` - chunk id to full chunk record

## Frontend

A Next.js 14 app. `src/lib/api.ts` is the typed wrapper for all backend calls. Chat answers
stream in through the SSE route, and the sources panel shows each source's page and units.
