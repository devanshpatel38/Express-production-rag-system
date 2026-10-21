"""Text normalization for text extracted from the Ghostscript-produced GEP PDF.

Pure function, no I/O. Handles three artifacts seen in the extracted text:
- U+FFFD replacement characters. Ghostscript emits one where a curly
  apostrophe or quote was. A U+FFFD flanked by letters on both sides is
  taken to be an apostrophe (Fed�s -> Fed's); any other one becomes a
  straight double quote.
- common UTF-8 mojibake sequences (text decoded as cp1252/latin-1), mapped
  to the intended punctuation.
- hyphenated words split across line breaks, and messy whitespace. Joins
  are skipped where a digit sits on either side, so numeric ranges such as
  2019-\n2020 keep their hyphen and both numbers.
"""

import re

# Known mojibake (UTF-8 bytes decoded as cp1252) -> intended punctuation.
_MOJIBAKE = {
    "â\u0080\u0099": "'",  # right single quote
    "â\u0080\u0098": "'",  # left single quote
    "â\u0080\u009c": '"',  # left double quote
    "â\u0080\u009d": '"',  # right double quote
    "â\u0080\u0093": "–",  # en dash (kept as the dash, never "-")
    "â\u0080\u0094": "—",  # em dash (kept as the dash, never "-")
}

_REPLACEMENT_CHAR = "�"
# Letter-hyphen-newline-letter, where neither side is a digit. Lookarounds keep
# the joined letters out of the match, so only the hyphen and break are removed.
_HYPHEN_BREAK = re.compile(r"(?<=[^\W\d])-\n[ \t]*(?=[^\W\d])")
_FFFD_BETWEEN_LETTERS = re.compile(r"(?<=\w)�(?=\w)")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_INLINE_SPACE = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """Repair artifacts, de-hyphenate line breaks, and collapse whitespace.

    Paragraph breaks (blank lines) are kept as a single "\\n\\n"; all other
    whitespace runs, including single line breaks, collapse to one space.
    """
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # De-hyphenate before the mojibake pass, so no dash produced there can
    # ever be mistaken for a line-break hyphen.
    s = _HYPHEN_BREAK.sub("", s)
    for bad, good in _MOJIBAKE.items():
        s = s.replace(bad, good)
    s = _FFFD_BETWEEN_LETTERS.sub("'", s)
    s = s.replace(_REPLACEMENT_CHAR, '"')

    paragraphs = _PARAGRAPH_BREAK.split(s)
    cleaned = (_INLINE_SPACE.sub(" ", p).strip() for p in paragraphs)
    return "\n\n".join(p for p in cleaned if p)
