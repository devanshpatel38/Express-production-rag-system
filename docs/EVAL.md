# Evaluation

The eval harness lives in `backend/eval/`. It runs the live pipeline (hybrid
retrieval, Cohere rerank, LLM answer) over a verified set of questions about the
GPO 2018 Annual Report, scores the results with Ragas, and fails CI when a score
drops below its floor.

## Dataset

`backend/eval/dataset.json` holds 15 hand-curated questions: 9 about financial
numbers and 6 about the narrative sections. The financial answers were checked
against the report's own tables, and the narrative answers against the report text.

Each item has:

- `id` - a short name for the question.
- `question` - the prompt sent to the pipeline.
- `ground_truth` - the reference answer used by the Ragas metrics.
- `reference_pages` - the 1-based PDF pages where the answer is found. Used for the
  page-based retrieval hit-rate.

Add new questions by appending to the `items` list in this file.

## Metrics

Four Ragas metrics, plus a retrieval hit-rate and latency:

| Metric | What it measures | Floor |
| --- | --- | --- |
| `faithfulness` | Are the claims in the answer supported by the retrieved chunks? | 0.70 |
| `answer_relevancy` | Does the answer address the question? | 0.70 |
| `context_precision` | Of the retrieved chunks, how many are relevant? | 0.55 |
| `context_recall` | How much of the information needed to answer was retrieved? | 0.55 |
| Retrieval hit-rate | Share of questions where at least one retrieved chunk comes from a reference page. | reported |
| Latency p50 | Median end-to-end time per question, in milliseconds. | reported |

The floors are defined in `backend/eval/run_eval.py` under `THRESHOLDS`.

## Running it

```bash
cd backend
python -m eval.run_eval                     # full run, prints and saves a report
python -m eval.run_eval --check-thresholds  # CI mode, exits non-zero if a metric is below its floor
python -m eval.run_eval --output path.json  # choose where the JSON report is written
```

The harness sends each question through the pipeline, collects the answer and the
reranked chunks, then scores them. The run prints the retrieval hit-rate, p50
latency, and each Ragas score (flagging any that fall below the floor). The JSON
report is saved to `backend/eval/reports/<timestamp>.json`.

Ragas needs a scoring LLM. Set `OPENAI_API_KEY`, or set `GEMINI_API_KEY` with
`langchain-google-genai` installed (it is in `requirements.txt`).

## CI

`.github/workflows/eval.yml` runs on pull requests that touch `backend/**` and can
also be started manually. The job:

1. Builds a fresh index from the GPO report PDF.
2. Runs `python -m eval.run_eval --check-thresholds`.
3. Uploads the JSON report as a workflow artifact (kept 30 days).
4. Posts the hit-rate, p50 latency, and score table as a comment on the pull request.

If any metric is below its floor the workflow fails, which blocks merge when branch
protection is on.

### Secrets

Set these under Settings, Secrets and variables, Actions:

- `OPENAI_API_KEY` - answers and Ragas scoring in CI.
- `COHERE_API_KEY` - turns on the Cohere reranker.

## Reading the results

- **Low context_precision** - the reranker is letting noise through. Try fewer
  candidates before reranking.
- **Low context_recall** - the retriever is missing the right chunks. Check chunk
  size and try adjusting `HYBRID_ALPHA`.
- **Low faithfulness with good context_precision** - tighten the system prompt,
  lower the temperature, or use a stronger model.
- **Low answer_relevancy with good context** - add clearer format and length
  guidance to the prompt.
