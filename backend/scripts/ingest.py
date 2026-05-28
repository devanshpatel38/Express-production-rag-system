"""Ingest CLI.

Usage:
    python -m scripts.ingest --source /path/to/expressjs.com/en
    python -m scripts.ingest --source ./external/express-docs/en

Walks markdown files, chunks them, builds Chroma + BM25 indices, persists to disk.
Run this once locally, commit the resulting `data/` (or rebuild on deploy).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.config import get_settings
from app.ingestion.chunker import chunk_markdown
from app.ingestion.indexer import build_indices
from app.ingestion.loader import iter_markdown_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Express.js markdown docs into the RAG index.")
    parser.add_argument(
        "--source",
        required=True,
        help="Path to a directory containing Express markdown docs (e.g. cloned expressjs.com/en).",
    )
    args = parser.parse_args()

    s = get_settings()
    root = Path(args.source).resolve()
    print(f"Ingesting from: {root}")
    print(f"Chunk size={s.chunk_size}, overlap={s.chunk_overlap}")

    all_chunks = []
    files_seen = 0
    for rel_path, text in iter_markdown_files(root):
        files_seen += 1
        chunks = chunk_markdown(
            text=text,
            source_path=str(rel_path),
            chunk_size=s.chunk_size,
            chunk_overlap=s.chunk_overlap,
        )
        all_chunks.extend(chunks)

    print(f"Processed {files_seen} files → {len(all_chunks)} chunks")
    if not all_chunks:
        raise SystemExit("No chunks produced - check the --source path points at markdown files.")

    summary = build_indices(all_chunks)
    print("Done.")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
