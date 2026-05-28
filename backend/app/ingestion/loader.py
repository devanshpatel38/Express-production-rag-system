"""Loads markdown files from a local clone of the Express docs repo.

We point this at expressjs/expressjs.com (the docs source) and just walk its
en/ subtree. Each file becomes one or more chunks downstream.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator


# Express docs repo organises content under en/. We skip non-content paths.
_SKIP_DIRS = {"_includes", "_layouts", "_data", "node_modules", ".git"}


def iter_markdown_files(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield (path, text) for every markdown file under root.

    Paths are returned relative to root so they're stable across machines.
    """
    if not root.exists():
        raise FileNotFoundError(f"Docs root not found: {root}")

    for path in root.rglob("*.md"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # A handful of files in random repos aren't utf-8; skip rather than die.
            continue
        if not text.strip():
            continue
        yield path.relative_to(root), text
