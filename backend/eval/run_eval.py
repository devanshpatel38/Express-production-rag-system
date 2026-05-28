"""Eval harness.

Runs the dataset through the live pipeline, captures retrieved contexts and
generated answers, then scores them with Ragas. The score thresholds in
`check_thresholds` are what CI uses to fail PRs that regress quality.

Usage:
    python -m eval.run_eval                     # full run, prints + writes report
    python -m eval.run_eval --check-thresholds  # also exits non-zero if scores drop
"""
from __future__ import annotations

import argparse
import json
import time
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.models.schemas import ChatMessage
from app.rag.pipeline import run_pipeline


# Score floors. Tune these as the system improves; CI fails any PR that drops below.
THRESHOLDS = {
    "faithfulness": 0.70,
    "answer_relevancy": 0.70,
    "context_precision": 0.55,
    "context_recall": 0.55,
}

EVAL_FILE = Path(__file__).parent / "dataset.json"
REPORT_DIR = Path(__file__).parent / "reports"


def _load_dataset() -> list[dict]:
    with EVAL_FILE.open(encoding="utf-8") as f:
        return json.load(f)["items"]


def _run_pipeline_collect(items: list[dict]) -> list[dict]:
    """Run the live pipeline against each item and capture rows in Ragas's expected shape."""
    rows: list[dict] = []
    for it in items:
        print(f"[run] {it['id']}")
        result = run_pipeline(query=it["question"], history=[])
        rows.append(
            {
                "question": it["question"],
                "answer": result.answer,
                "contexts": [c.text for c in result.post_rerank],
                "ground_truth": it["ground_truth"],
                "_id": it["id"],
                "_latency_ms": result.latency_ms,
                "_retrieved_paths": [c.source_path for c in result.post_rerank],
                "_reference_sources": it.get("reference_sources", []),
            }
        )
        time.sleep(20)
    return rows


def _score_with_ragas(rows: list[dict]) -> dict:
    """Run Ragas metrics. Ragas needs an LLM + embeddings for some metrics; we reuse ours."""
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    # Ragas pulls its LLM from env (OPENAI_API_KEY) by default. If we're on Gemini we
    # still want a working scorer - the LangChain wrapper lets us inject it manually.
    llm = None
    embeddings = None
    if not os.environ.get("OPENAI_API_KEY"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from ragas.llms import LangchainLLMWrapper

            llm = LangchainLLMWrapper(
                ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.0)
            )
            embeddings = LangchainEmbeddingsWrapper(
                GoogleGenerativeAIEmbeddings(model="models/embedding-001")
            )
        except ImportError:
            print(
                "[warn] No OPENAI_API_KEY and langchain-google-genai not installed. "
                "Ragas may fail."
            )

    ds = Dataset.from_list(
        [
            {
                "question": r["question"],
                "answer": r["answer"],
                "contexts": r["contexts"],
                "ground_truth": r["ground_truth"],
            }
            for r in rows
        ]
    )

    result = evaluate(
        ds,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=llm,
        embeddings=embeddings,
    )
    # Ragas returns per-row scores plus aggregate.
    df = result.to_pandas()
    aggregate = {col: float(df[col].mean()) for col in THRESHOLDS}
    return {"aggregate": aggregate, "rows": df.to_dict(orient="records")}


def _retrieval_hit_rate(rows: list[dict]) -> float:
    """A simple sanity metric: does the retrieved set intersect any reference source?"""
    relevant = [r for r in rows if r["_reference_sources"]]
    if not relevant:
        return 1.0
    hits = 0
    for r in relevant:
        refs = set(r["_reference_sources"])
        got = set(r["_retrieved_paths"])
        if refs & got:
            hits += 1
    return hits / len(relevant)


def _print_report(aggregate: dict, hit_rate: float, latency_p50: int) -> None:
    print("\n=== Eval Report ===")
    print(f"Retrieval hit-rate: {hit_rate:.2%}")
    print(f"Latency p50: {latency_p50} ms")
    for k, v in aggregate.items():
        floor = THRESHOLDS.get(k)
        flag = "" if floor is None or v >= floor else "  ⚠ BELOW THRESHOLD"
        print(f"  {k:20s} {v:.3f}{flag}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-thresholds",
        action="store_true",
        help="Exit non-zero if any metric falls below its threshold (CI mode).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to write the JSON report. Defaults to eval/reports/<timestamp>.json.",
    )
    args = parser.parse_args()

    items = _load_dataset()
    rows = _run_pipeline_collect(items)

    hit_rate = _retrieval_hit_rate(rows)
    latencies = sorted(r["_latency_ms"] for r in rows)
    latency_p50 = latencies[len(latencies) // 2] if latencies else 0

    scored = _score_with_ragas(rows)
    aggregate = scored["aggregate"]

    _print_report(aggregate, hit_rate, latency_p50)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = args.output or REPORT_DIR / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(
        json.dumps(
            {
                "aggregate": aggregate,
                "retrieval_hit_rate": hit_rate,
                "latency_p50_ms": latency_p50,
                "rows": scored["rows"],
            },
            indent=2,
        )
    )
    print(f"\nReport saved → {out_path}")

    if args.check_thresholds:
        failures = [k for k, v in aggregate.items() if v < THRESHOLDS[k]]
        if failures:
            print(f"\nThreshold failures: {failures}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
