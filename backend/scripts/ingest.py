"""Ingest CLI for the GPO annual report PDF.

Usage:
    python -m scripts.ingest --source ../GPO-Anual-report.pdf [--max-pages N]

Flow: load_pdf -> chunk_pages -> stamp source_path (PDF basename) -> build_indices.
build_indices wipes and rebuilds the Chroma collection, BM25 pickle and docs_meta.json.
"""
from __future__ import annotations

import argparse
import os
from collections import Counter

from app.config import get_settings
from app.ingestion.indexer import build_indices
from app.ingestion.pdf_chunker import chunk_pages
from app.ingestion.pdf_loader import load_pdf


def run_ingest(source: str, max_pages: int | None = None) -> dict:
    s = get_settings()
    print(f"Ingesting from: {source}")
    print(f"Chunk size={s.chunk_size}, overlap={s.chunk_overlap}")

    pages = load_pdf(source, max_pages=max_pages)
    chunks = chunk_pages(pages, s.chunk_size, s.chunk_overlap)
    if not chunks:
        raise SystemExit("No chunks produced - check --source points at a text PDF.")

    # Chunks default source_path to "page-N"; citations should name the PDF.
    basename = os.path.basename(source)
    for c in chunks:
        c.source_path = basename

    counts = Counter(c.chunk_type or "prose" for c in chunks)
    print(f"Loaded {len(pages)} pages -> {len(chunks)} chunks")
    for chunk_type, n in sorted(counts.items()):
        print(f"  {chunk_type}: {n}")

    summary = build_indices(chunks)
    summary["counts_by_type"] = dict(counts)
    print("Done.")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the GPO annual report PDF into the RAG index.")
    parser.add_argument("--source", required=True, help="Path to the PDF (e.g. ../GPO-Anual-report.pdf).")
    parser.add_argument("--max-pages", type=int, default=None, help="Only ingest the first N pages.")
    args = parser.parse_args()
    run_ingest(args.source, max_pages=args.max_pages)


if __name__ == "__main__":
    main()
