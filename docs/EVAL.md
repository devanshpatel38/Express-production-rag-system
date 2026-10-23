# Evaluation

The eval harness lives in `backend/eval/`. It runs the live pipeline (hybrid
retrieval, Cohere rerank, LLM answer) over a verified set of questions about the
Global Economic Prospects report, scores the results with Ragas, and checks them
against score floors in CI.

## Dataset

`backend/eval/dataset.json` holds 14 question and answer items. Each answer was
checked against the report PDF. The questions cover exact figures from the data
tables (for example GDP growth forecasts for the world, India and the United
States), narrative points from the report text, and what individual figure panels
show.

Each item has:

- `id` — a short name for the item.
- `question` — the prompt sent to the pipeline.
- `ground_truth` — the reference answer used by Ragas.
- `reference_pages` — the 1-based PDF page numbers where the answer is found. Used
  for the page-based retrieval hit-rate.
- `requires_vision` — set on items whose answer comes from a figure description.

To grow the set, add more items to the `items` list in this file.

## Metrics

Four Ragas metrics are scored, along with a retrieval hit-rate and latency:

| Metric | What it measures | Floor |
| --- | --- | --- |
| `faithfulness` | Are the claims in the answer supported by the retrieved chunks? | 0.70 |
| `answer_relevancy` | Does the answer address the question? | 0.70 |
| `context_precision` | Of the chunks sent to the LLM, how many are relevant? | 0.55 |
| `context_recall` | How much of the information needed to answer was retrieved? | 0.55 |
| `retrieval_hit_rate` | Share of questions where at least one retrieved chunk comes from a `reference_pages` page. | reported |
| `latency_p50_ms` | Median end-to-end pipeline latency per question. | reported |

The floors are defined in `backend/eval/run_eval.py` under `THRESHOLDS`.

## Running the eval

```bash
cd backend
python -m eval.run_eval                     # full run, prints and saves a report
python -m eval.run_eval --check-thresholds  # CI mode: non-zero exit if a metric is below its floor
```

Options:

- `--output <path>` — write the JSON report to a specific file.
- `--skip-vision-items` — run only the items that do not need figure descriptions.
  Use this when the index was built with `--no-vision`.

Every question is sent through the live pipeline, and the retrieved chunks and
generated answer are passed to Ragas. Ragas needs a scoring LLM: set
`OPENAI_API_KEY`, or set `GEMINI_API_KEY` with `langchain-google-genai` installed
(it is in `requirements.txt`).

Reports are written to `backend/eval/reports/<timestamp>.json`. Each report holds
the aggregate scores, the retrieval hit-rate, the p50 latency, and per-question
scores.

## CI

`.github/workflows/eval.yml` runs on pull requests that touch `backend/**` and can
also be started manually. The job:

1. Installs the backend dependencies.
2. Checks that `GEP-Jun-2026.pdf` is at the repo root.
3. Builds the index with `scripts.ingest --no-vision`.
4. Runs `eval.run_eval --check-thresholds --skip-vision-items`.
5. Uploads the JSON report as a workflow artifact (kept 30 days).
6. Posts the hit-rate, latency and score table as a comment on the pull request.

If any metric falls below its floor, the job exits non-zero.

### Secrets

Set these under Settings, Secrets and variables, Actions:

- `OPENAI_API_KEY` — used for the answer LLM and for Ragas scoring.
- `COHERE_API_KEY` — enables the Cohere reranker.

## Reading the results

- **Low `context_precision`** — the reranker is letting weak chunks through. Try
  fewer candidates or a stronger rerank model.
- **Low `context_recall`** — the retriever is missing the right chunks. Check
  chunking and try changing `HYBRID_ALPHA`.
- **Low `faithfulness` with good `context_precision`** — tighten the system prompt,
  lower the temperature, or use a stronger model.
- **Low `answer_relevancy` with good context** — add clearer format and length
  guidance to the prompt.
- **Low `retrieval_hit_rate`** — the right pages are not reaching the top results;
  check the page and units metadata on the indexed chunks.
