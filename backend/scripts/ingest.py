"""Ingest CLI (PDF path).

Usage:
    python -m scripts.ingest --source ../GEP-Jun-2026.pdf [--max-pages N] [--no-vision]

load_pdf -> chunk_pages -> (stamp source_path) -> build_indices. Wipes and rebuilds
the Chroma + BM25 + docs_meta indices. Prints chunk counts by chunk_type.
"""
from __future__ import annotations

import argparse
import os
from collections import Counter

from app.config import get_settings
from app.ingestion.indexer import build_indices
from app.ingestion.pdf_chunker import chunk_pages
from app.ingestion.pdf_loader import load_pdf


class _NoopDescriber:
    """Figure describer that makes no LLM call; figures it yields are dropped."""

    def describe(self, png_bytes: bytes, caption: str) -> str:
        return ""


def run_ingest(source: str, max_pages: int | None = None, no_vision: bool = False) -> dict[str, int]:
    """Build the indices from a PDF. Returns chunk counts by chunk_type."""
    s = get_settings()
    pages = load_pdf(
        source,
        describe_figures_fn=_NoopDescriber() if no_vision else None,
        max_pages=max_pages,
    )
    if no_vision:
        for p in pages:
            p.figures = [f for f in p.figures if f.description.strip()]

    chunks = chunk_pages(pages, s.chunk_size, s.chunk_overlap)
    if not chunks:
        raise SystemExit("No chunks produced - check --source points at a text PDF.")

    # R11: chunkers leave source_path empty; cite the PDF by basename.
    name = os.path.basename(source)
    for c in chunks:
        c.source_path = name

    summary = build_indices(chunks)
    counts = dict(Counter(c.chunk_type for c in chunks))
    print(f"Pages loaded: {len(pages)}; total chunks: {len(chunks)}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the GEP PDF into the RAG index.")
    parser.add_argument("--source", required=True, help="Path to the PDF (e.g. ../GEP-Jun-2026.pdf).")
    parser.add_argument("--max-pages", type=int, default=None, help="Only process the first N pages.")
    parser.add_argument("--no-vision", action="store_true", help="Skip figure description (no LLM calls).")
    args = parser.parse_args()
    run_ingest(args.source, args.max_pages, args.no_vision)
    print("Done.")


if __name__ == "__main__":
    main()
