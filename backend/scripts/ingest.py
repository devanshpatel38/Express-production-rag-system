"""Ingest CLI for the iMac PER report.

Usage (from backend/):
    python -m scripts.ingest
    python -m scripts.ingest --source ../iMac_PER_Oct2024.pdf

Pipeline: load_pdf -> chunk_document -> build_indices (Chroma + BM25 + docs_meta.json).
"""
from __future__ import annotations

import argparse
from collections import Counter

from app.config import get_settings
from app.ingestion.indexer import build_indices
from app.ingestion.pdf_chunker import chunk_document
from app.ingestion.pdf_loader import load_pdf


def run(source: str | None = None) -> dict:
    s = get_settings()
    source = source or s.source_pdf_path
    print(f"Ingesting from: {source}")

    doc = load_pdf(source)
    print(f"Loaded {len(doc.pages)} pages")

    chunks = chunk_document(doc, chunk_size=s.chunk_size, chunk_overlap=s.chunk_overlap)
    counts = Counter(c.chunk_type for c in chunks)
    print(
        f"Chunked into {len(chunks)} chunks "
        f"(prose={counts.get('prose', 0)}, table_row={counts.get('table_row', 0)})"
    )
    if not chunks:
        raise SystemExit("No chunks produced - check the --source path points at the iMac PDF.")

    summary = build_indices(chunks)
    print("Done.")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  docs_meta_path: {s.docs_meta_path}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the iMac PER PDF into the RAG index.")
    parser.add_argument("--source", default=None, help="PDF path (default: settings.source_pdf_path).")
    run(parser.parse_args().source)


if __name__ == "__main__":
    main()
