# Evaluation

The eval harness lives in `backend/eval/`. It runs the live pipeline against a
hand-curated dataset, scores the outputs with Ragas, and fails CI on regression.

## Dataset

`backend/eval/dataset.json` — 13 items as of v1, covering routing, middleware,
error handling, static files, body parsing, sub-routers, production tips,
template engines, cookie parsing, proxies, and one deliberately off-topic
question (to check the system declines rather than hallucinates).

Each item has:

- `question` — the prompt we send.
- `ground_truth` — a short reference answer used by Ragas's answer-grounded metrics.
- `reference_sources` — markdown paths we *expect* the retriever to surface.
  Used for our custom `retrieval_hit_rate` metric.

Grow the set by appending to this file. ~50 items is a good target for stable
metric variance; we ship 13 to keep CI fast.

## Metrics

We rely on four Ragas metrics plus one of our own:

| Metric | What it measures | Threshold |
| --- | --- | --- |
| `faithfulness` | Are claims in the answer supported by the retrieved context? Catches hallucination. | 0.70 |
| `answer_relevancy` | Does the answer actually address the question? | 0.70 |
| `context_precision` | Of the retrieved chunks, how many are relevant? Reranker quality signal. | 0.55 |
| `context_recall` | Of the info needed to answer, how much did we retrieve? Retriever quality signal. | 0.55 |
| `retrieval_hit_rate` *(custom)* | Did at least one retrieved chunk come from a `reference_source` file? | (informational) |

Thresholds live in `eval/run_eval.py` under `THRESHOLDS`. Bump them up over time —
that's the whole point of having them in code.

## Why these floors

The floors were set by running the full pipeline a few times to get a noise
baseline, then setting thresholds ~10% below the median observed score. The
goal is to catch regressions, not to gate on absolute quality — you'll fail PRs
that meaningfully drop something, but pass small noise.

## CI integration

`.github/workflows/eval.yml` runs the harness on every PR that touches
`backend/**`. The job:

1. Clones the Express docs.
2. Builds a fresh index.
3. Runs `eval.run_eval --check-thresholds`.
4. Posts a comment on the PR with the score table.
5. Uploads the full JSON report as a workflow artifact (kept 30 days).

Failing a metric makes the workflow exit non-zero, which blocks merge if
branch protection is on.

### Required secrets

Set these on the repo (Settings → Secrets and variables → Actions):

- `GEMINI_API_KEY` (or `OPENAI_API_KEY` — Ragas needs *some* LLM for scoring)
- `COHERE_API_KEY` (optional; if absent, reranker is skipped)

## Local runs

```bash
cd backend
python -m eval.run_eval                  # interactive, prints + saves report
python -m eval.run_eval --check-thresholds  # CI mode
```

Reports drop into `backend/eval/reports/<timestamp>.json`. They're gitignored —
keep them around locally if you want to compare runs.

## Extending

Common moves when working on quality:

- **Bad context_precision** → reranker is letting noise through. Try a stronger
  rerank model or pull fewer pre-rerank candidates.
- **Bad context_recall** → retriever is missing the right chunks. Inspect what
  did come back, check chunking (too small? too big?), try shifting `HYBRID_ALPHA`.
- **Bad faithfulness with good context_precision** → prompt issue or LLM
  hallucinating. Tighten the system prompt, lower temperature, or upgrade the model.
- **Bad answer_relevancy with good context** → prompt is letting the model
  ramble. Add explicit format/length guidance.
