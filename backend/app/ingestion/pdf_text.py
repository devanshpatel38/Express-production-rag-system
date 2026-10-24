"""Pure text-normalisation helpers for text extracted from PDFs.

No PDF dependency: everything here is string -> string so it is fast to test.

Public API
----------
normalize_text(text) -> str
detect_running_header(pages, min_fraction=0.5) -> str | None
strip_running_headers(pages, min_fraction=0.5) -> tuple[list[str], str | None]
"""
from __future__ import annotations

import re
from collections import Counter

DIGIT_PLACEHOLDER = "#"

# Common UTF-8-read-as-cp1252 sequences, checked before the generic repair.
_MOJIBAKE = {
    "\u00e2\u0080\u0099": "'", "\u00e2\u20ac\u2122": "'",
    "\u00e2\u20ac\u02dc": "'", "\u00e2\u20ac\u0153": '"',
    "\u00e2\u20ac\u009d": '"', "\u00e2\u20ac\u201c": "-",
    "\u00e2\u20ac\u201d": "-", "\u00e2\u20ac\u00a6": "...",
    "\u00e2\u20ac\u00a2": "\u2022", "\u00c2\u00a0": " ", "\u00c2\u00b0": "\u00b0",
    "\u00c2\u00a9": "\u00a9", "\u00c2\u00ae": "\u00ae",
}
# A cluster that looks like mis-decoded UTF-8 (lead char + continuation-ish chars).
_MOJI_RE = re.compile("[\u00c2\u00c3\u00e2][\u0080-\u00bf\u0152-\u2122\u20ac]+")

_SMART = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2010": "-", "\u2011": "-",
    "\u2026": "...", "\u00ad": "",  # soft hyphen
    "\u200b": "", "\ufeff": "",
}
_SMART_RE = re.compile("|".join(map(re.escape, _SMART)))
# Unicode spaces (incl. nbsp) except newline-ish characters.
_UNI_SPACE_RE = re.compile("[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000\t\f\v]")
_LETTER = r"[^\W\d_]"
_DEHYPHEN_RE = re.compile(rf"(?<={_LETTER})-[ \t]*\n[ \t]*(?={_LETTER})")


def _fix_mojibake(text: str) -> str:
    for bad, good in _MOJIBAKE.items():
        text = text.replace(bad, good)

    def _repair(m: re.Match) -> str:
        try:
            return m.group(0).encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return m.group(0)

    return _MOJI_RE.sub(_repair, text)


def normalize_text(text: str) -> str:
    """Repair mojibake, normalise spaces/punctuation, de-hyphenate line wraps.

    De-hyphenation drops "-\n" only when both sides are letters; between
    digits the hyphen is kept and the newline removed ("2024-\n25" ->
    "2024-25"). Paragraph breaks are preserved; inline whitespace collapses.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _fix_mojibake(text)
    text = _SMART_RE.sub(lambda m: _SMART[m.group(0)], text)
    text = _UNI_SPACE_RE.sub(" ", text)
    text = _DEHYPHEN_RE.sub("", text)
    # Non-letter hyphen line wrap (e.g. digits): keep hyphen, drop the newline.
    text = re.sub(r"(?<=\d)-[ \t]*\n[ \t]*(?=\d)", "-", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _mask(line: str) -> str:
    return re.sub(r"\d+", DIGIT_PLACEHOLDER, re.sub(r"\s+", " ", line.strip()))


def _is_numeric_only(masked: str) -> bool:
    """True if nothing but placeholders/whitespace/punctuation remains."""
    return not re.search(r"[^\W\d_]", masked)


def _header_templates(pages: list[str], min_fraction: float) -> set[str]:
    if len(pages) < 2:
        return set()
    counts: Counter[str] = Counter()
    for page in pages:
        seen = {_mask(l) for l in page.splitlines() if l.strip()}
        counts.update(m for m in seen if not _is_numeric_only(m))
    need = max(2, int(len(pages) * min_fraction + 0.9999))
    return {m for m, c in counts.items() if c >= need}


def detect_running_header(pages: list[str], min_fraction: float = 0.5) -> str | None:
    """Return the most frequent running-header template, or None.

    The template is the digit-masked line (digits become "#"), e.g.
    "iMac | Product Environmental Report #". Numeric-only lines never qualify.
    """
    templates = _header_templates(pages, min_fraction)
    if not templates:
        return None
    counts: Counter[str] = Counter()
    for page in pages:
        counts.update({_mask(l) for l in page.splitlines() if _mask(l) in templates})
    return counts.most_common(1)[0][0]


def strip_running_headers(
    pages: list[str], min_fraction: float = 0.5
) -> tuple[list[str], str | None]:
    """Remove lines recurring across pages (digit-masked) from every page.

    Returns (cleaned_pages, header_template). header_template is the same
    value as detect_running_header(pages) (e.g. "iMac | Product Environmental
    Report #"), or None if nothing was detected. Numeric-only lines are never
    removed.
    """
    templates = _header_templates(pages, min_fraction)
    if not templates:
        return list(pages), None
    cleaned = []
    for page in pages:
        kept = [l for l in page.splitlines() if _mask(l) not in templates]
        cleaned.append("\n".join(kept).strip("\n"))
    return cleaned, detect_running_header(pages, min_fraction)
