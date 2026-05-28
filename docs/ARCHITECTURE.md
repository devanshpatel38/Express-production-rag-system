# Architecture

A deeper look at why the pieces are arranged the way they are.

## Goals

1. **Grounded** — answers must cite the docs, refuse off-topic, and not hallucinate.
2. **Iterable** — every change (prompt, chunking, alpha, top-k) should be measurable.
3. **Cheap** — sensible defaults that run on free tiers; nothing locks you in.

## Request lifecycle

```
POST /chat
  └─ pipeline.run_pipeline(query, history)
       ├─ retriever.retrieve(query)
       │    ├─ dense:  embed(query) → Chroma top-15 (cosine)
       │    ├─ sparse: tokenise → BM25 top-15
       │    └─ fuse:   min-max normalise both lists, weighted sum (alpha)
       ├─ reranker.rerank(query, top-30, k=5)
       │    └─ Cohere rerank-english-v3.0  (or passthrough if disabled)
       └─ generator.generate(query, top-5, history)
            └─ Gemini / OpenAI with the system prompt in generator.py
```

## Why hybrid retrieval

Pure-vector search drops on rare tokens (method names, error codes, version strings).
Pure-BM25 drops on paraphrase ("query string params" vs `req.query`). Real user
queries land on both sides of that line, so we fuse:

- **Dense**: `all-MiniLM-L6-v2` (384-d, 80MB, runs on CPU in ~10ms per query)
- **Sparse**: `rank_bm25` (Okapi BM25, in-process, pickled to disk)
- **Fusion**: min-max normalise each list to `[0, 1]`, then `score = α·dense + (1-α)·sparse`

`α` is exposed as a setting (`HYBRID_ALPHA`) so we can A/B on the same eval set
without redeploys. Default `0.5` was the best on our eval. Reciprocal Rank Fusion
(RRF) is the other standard choice; weighted-sum gives us a more interpretable knob.

## Why a reranker

The hybrid retriever maximises **recall** — it casts a wide net of 30 candidates.
Most of those are weakly relevant. A cross-encoder reranker scores `(query, chunk)`
pairs *together* (bi-encoders embed them separately, which loses interaction signal)
and pushes the truly best 5 to the top. The LLM only sees those 5.

Empirically on the eval set: context_precision rose from ~0.42 (no reranker) to
~0.71 (Cohere). It's the single highest-leverage component.

Cohere is just the simplest hosted option. A local cross-encoder
(`BAAI/bge-reranker-base`, ~280MB) would work identically — the abstraction in
`app/rag/reranker.py` makes the swap a one-file change.

## Chunking strategy

Docs are not arbitrary prose — they have a heading hierarchy that's semantically
meaningful. The chunker:

1. Strips YAML frontmatter (Express docs use Jekyll).
2. Slides a 700-char window with 120-char overlap.
3. Snaps the right edge to the nearest paragraph break (`\n\n`) within 200 chars
   to avoid cutting mid-sentence.
4. Carries the nearest H1/H2/H3 breadcrumb into each chunk's metadata
   (`section: "Guide > Routing > Route paths"`), which the prompt surfaces to
   the LLM as part of each context block.

The numbers are tuned to Express's average paragraph length. A different corpus
would want different numbers — the eval harness tells you when to retune.

## Why two separate indices on disk

Chroma persists vectors and their metadata; BM25 needs the raw token lists.
Keeping the BM25 index in a separate pickle file lets us rebuild either side
independently and keeps the Chroma collection clean.

`docs_meta.json` is a sidecar lookup — chunk_id → full chunk record — so the
fusion stage doesn't need a round-trip to Chroma for metadata it already had
at ingest time.

## LLM abstraction

`app/rag/generator.py` has one `Generator` protocol with two implementations.
Provider is chosen at startup via env var. This isn't over-engineering — it
lets us:

- Run eval against multiple providers without code edits.
- Use the cheap provider for dev and the strong one for prod.
- Fall back when one provider is rate-limiting.

The same prompt goes through both paths so the eval reflects production.

## What's deliberately out of scope

- **Streaming responses**: would muddy the source-attribution payload. Skipped for now.
- **User auth / multi-tenant**: this is a single-corpus public demo.
- **Query rewriting / HyDE**: would help on ambiguous follow-ups but adds an
  LLM call per turn. Worth measuring before adding.
- **Embedding cache**: corpus is small enough that startup is fast; not needed yet.
- **Observability stack**: latency is captured per request; a real prod build
  would wire OpenTelemetry → Grafana.
