"""Markdown-aware chunker.

We chunk by character window with overlap, but also carry the nearest H1/H2
into each chunk's metadata so the prompt can show "in section: Routing" etc.
A header-aware chunker beats blind splitting by a wide margin on docs.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class Chunk:
    chunk_id: str
    source_path: str
    title: str        # nearest heading
    section: str      # full breadcrumb e.g. "Guide > Routing > Route paths"
    text: str
    char_start: int
    char_end: int

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source_path": self.source_path,
            "title": self.title,
            "section": self.section,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


@dataclass
class _HeadingSpan:
    level: int
    title: str
    start: int  # char offset where heading line begins


def _build_breadcrumb(headings: list[_HeadingSpan], pos: int) -> tuple[str, str]:
    """Return (nearest_title, breadcrumb) for a given character position."""
    active: list[_HeadingSpan] = []
    for h in headings:
        if h.start > pos:
            break
        # Pop deeper-or-equal levels - that's how heading nesting actually works.
        while active and active[-1].level >= h.level:
            active.pop()
        active.append(h)
    if not active:
        return ("(untitled)", "(untitled)")
    return (active[-1].title, " > ".join(h.title for h in active))


def _strip_frontmatter(md: str) -> str:
    # Express docs use Jekyll-style YAML frontmatter. We drop it.
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            return md[end + 4 :].lstrip("\n")
    return md


def chunk_markdown(
    text: str,
    source_path: str,
    chunk_size: int = 700,
    chunk_overlap: int = 120,
) -> list[Chunk]:
    """Slide a window over the markdown, snapping breaks to paragraph boundaries when possible."""
    text = _strip_frontmatter(text)
    if not text.strip():
        return []

    headings = [
        _HeadingSpan(level=len(m.group(1)), title=m.group(2).strip(), start=m.start())
        for m in HEADING_RE.finditer(text)
    ]

    chunks: list[Chunk] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + chunk_size, n)
        # Try to extend to a paragraph break so we don't cut mid-sentence.
        if end < n:
            window = text[end : min(end + 200, n)]
            nl = window.find("\n\n")
            if nl != -1:
                end = end + nl

        snippet = text[i:end].strip()
        if snippet:
            title, breadcrumb = _build_breadcrumb(headings, i)
            chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid4()),
                    source_path=source_path,
                    title=title,
                    section=breadcrumb,
                    text=snippet,
                    char_start=i,
                    char_end=end,
                )
            )
        if end >= n:
            break
        i = max(end - chunk_overlap, i + 1)

    return chunks
