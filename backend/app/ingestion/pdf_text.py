"""Text normalization for text extracted from the Ghostscript-produced GEP PDF.

Pure function, no I/O. Handles three artifacts seen in the extracted text:
- U+FFFD replacement characters (Ghostscript emits one for curly quotes),
- common UTF-8 mojibake sequences (text decoded as cp1252/latin-1),
- hyphenated words split across line breaks, and messy whitespace.
"""

import re

# Known mojibake (UTF-8 bytes decoded as cp1252) -> intended punctuation.
_MOJIBAKE = {
    "â\u0080\u0099": "'",  # right single quote
    "â\u0080\u0098": "'",  # left single quote
    "â\u0080\u009c": '"',  # left double quote
    "â\u0080\u009d": '"',  # right double quote
    "â\u0080\u0093": "-",  # en dash
    "â\u0080\u0094": "-",  # em dash
}

_REPLACEMENT_CHAR = "�"
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_INLINE_SPACE = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """Repair artifacts, de-hyphenate line breaks, and collapse whitespace.

    Paragraph breaks (blank lines) are kept as a single "\\n\\n"; all other
    whitespace runs, including single line breaks, collapse to one space.
    """
    for bad, good in _MOJIBAKE.items():
        s = s.replace(bad, good)
    # Ghostscript's replacement char stands in for a curly quote.
    s = s.replace(_REPLACEMENT_CHAR, '"')
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _HYPHEN_BREAK.sub(r"\1\2", s)

    paragraphs = _PARAGRAPH_BREAK.split(s)
    cleaned = (_INLINE_SPACE.sub(" ", p).strip() for p in paragraphs)
    return "\n\n".join(p for p in cleaned if p)
