# Evaluation

The eval harness runs the live pipeline (retrieve, rerank, generate) over a hand-verified
question set and scores the answers with [Ragas](https://docs.ragas.io).

## Dataset

`backend/eval/dataset.json` holds 16 questions about the iMac report. Each has a reference
answer and the page(s) of the report where the answer lives. The references were checked by
hand against the PDF.

## Metrics

| Metric | What it asks | Floor | Current |
| --- | --- | --- | --- |
| faithfulness | Is every claim in the answer backed by the retrieved chunks? | 0.70 | 0.73 |
| answer_relevancy | Does the answer actually address the question? | 0.70 | 0.97 |
| context_precision | Are the useful chunks ranked near the top of what was retrieved? | 0.55 | 0.87 |
| context_recall | Did retrieval bring back everything needed to match the reference answer? | 0.55 | 0.94 |
| page hit-rate | Does any retrieved chunk come from a reference page? | - | 100% |

The page hit-rate is a simple extra check that does not need an LLM judge: for each question
with reference pages, did retrieval return at least one chunk from one of those pages?

Faithfulness and answer relevancy judge the generator. Context precision and recall judge the
retriever and reranker.

## Thresholds

Defined in `backend/eval/run_eval.py` as `THRESHOLDS`:

| Metric | Floor |
| --- | --- |
| faithfulness | 0.70 |
| answer_relevancy | 0.70 |
| context_precision | 0.55 |
| context_recall | 0.55 |

## Running it

```bash
cd backend
python -m eval.run_eval                     # full run, writes a report to eval/reports/
python -m eval.run_eval --check-thresholds  # exits non-zero if any metric is below its floor
```

Options: `--output PATH` (report location), `--limit N` (first N questions), `--sleep SECONDS`
(pause between questions for rate limits).

Ragas needs a scoring LLM. Set `OPENAI_API_KEY`, or set `GEMINI_API_KEY` (the
`langchain-google-genai` package is in `requirements.txt`). The index must be built first.

## CI

`.github/workflows/eval.yml` runs `python -m eval.run_eval --check-thresholds` on pull
requests that touch `backend/`. The build fails if any metric drops below its floor, the
report is uploaded as an artifact, and a summary table (scores, hit-rate, latency) is posted
on the pull request.

## Tuning loop

Change one knob at a time (`HYBRID_ALPHA`, `TOP_K_RERANK`, `CHUNK_SIZE`, the reranker
on or off), re-ingest if chunking changed, and re-run the eval. Compare the new report with
the previous one.
