"""Pure text normalisation for PDF-extracted text (stdlib only).

Main job: collapse letter-spaced headers ("A N N U A L") without touching prose.
"""
from __future__ import annotations

import re

_MOJIBAKE = {
    "\u00e2\u20ac\u2122": "\u2019",
    "\u00e2\u20ac\u02dc": "\u2018",
    "\u00e2\u20ac\u0153": "\u201c",
    "\u00e2\u20ac\u009d": "\u201d",
    "\u00e2\u20ac\u201c": "\u2013",
    "\u00e2\u20ac\u201d": "\u2014",
    "\u00e2\u20ac\u00a6": "\u2026",
    "\u00c2\u00a0": " ",
    "\u00c2": "",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb00": "ff",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\u00a0": " ",
    "\u00ad": "",
    "\ufffd": "",
}
_MOJIBAKE_RE = re.compile("|".join(re.escape(k) for k in sorted(_MOJIBAKE, key=len, reverse=True)))

# letter + line-break hyphen + letter (digits on either side -> not joined)
_HYPHEN_BREAK = re.compile(r"(?<=[^\W\d_])-[ \t]*\r?\n[ \t]*(?=[^\W\d_])")

# A letter-spaced run: >=3 single-char tokens (letter or '.') separated by exactly one
# space, standing alone (bounded by whitespace / string edges), optionally followed by
# trailing punctuation glued to the last token ("R E P O R T."). Two+ spaces, '|', or any
# multi-char token end the run, so real words are never part of it.
# Only collapsed when genuinely header-like: all letters UPPERCASE and >=4 letters, or a
# dotted initialism ("U . S ."). Lower/mixed-case or short sequences are left alone.
_TOK = r"(?:[^\W\d_]|\.)"
_TRAIL = r"[.,:;)\]!?]*"
_ALPHA_RUN = re.compile(rf"(?<!\S)({_TOK}(?: {_TOK}){{2,}})({_TRAIL})(?!\S)")
# Spaced digits ("2 0 1 8"): >=4 single digits, to avoid touching "1 2 3" style lists.
_DIGIT_RUN = re.compile(rf"(?<!\S)(\d(?: \d){{3,}})({_TRAIL})(?!\S)")


def _join_alpha_run(m: re.Match) -> str:
    body, trail = m.group(1), m.group(2)
    toks = body.split(" ")
    alphas = [t for t in toks if t != "."]
    dots = len(toks) - len(alphas)
    if not all(t.isupper() for t in alphas):
        return m.group(0)
    # Real spaced header (>=4 caps), or a dotted initialism like "U . S ."
    if not (len(alphas) >= 4 or (dots >= 2 and len(alphas) >= 2)):
        return m.group(0)
    out: list[str] = []
    n = len(toks)
    for i, t in enumerate(toks):
        out.append(t)
        if t == "." and i + 1 < n:
            # initialism continues ("U.S.") if the next letter is itself followed by a dot
            if not (i + 2 < n and toks[i + 2] == "."):
                out.append(" ")
    return "".join(out) + trail


def _collapse_letter_spacing(line: str) -> str:
    line = _ALPHA_RUN.sub(_join_alpha_run, line)
    return _DIGIT_RUN.sub(lambda m: m.group(1).replace(" ", "") + m.group(2), line)


def normalize_text(s: str) -> str:
    """Repair encoding, de-hyphenate, collapse letter-spacing and inline whitespace."""
    if not s:
        return ""
    s = _MOJIBAKE_RE.sub(lambda m: _MOJIBAKE[m.group(0)], s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _HYPHEN_BREAK.sub("", s)
    lines = [_collapse_letter_spacing(ln) for ln in s.split("\n")]
    s = "\n".join(lines)
    s = re.sub(r"[ \t\f\v]+", " ", s)
    s = re.sub(r" ?\n ?", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# ---------------------------------------------------------------------------
# Running headers / footers and section breadcrumbs
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^Section\s+(?:[IVXLCDM]+|\d+)\s*:\s*\S.*$")


def _template(line: str) -> str:
    """Digit-masked form of a line: every digit becomes '#', so 'Page 12' == 'Page 7'."""
    return re.sub(r"\d", "#", line.strip())


def collect_repeating_lines(
    pages_top_bottom: list[tuple[str, str]], min_recurrence: int
) -> set[str]:
    """Return digit-masked templates of top/bottom lines recurring >= min_recurrence times.

    Numeric-only templates (no alphabetic character, e.g. page numbers or years) are
    excluded so that they are never stripped from body text.
    """
    counts: dict[str, int] = {}
    for top, bottom in pages_top_bottom:
        for line in (top, bottom):
            t = _template(line)
            if t:
                counts[t] = counts.get(t, 0) + 1
    return {
        t
        for t, n in counts.items()
        if n >= min_recurrence and any(c.isalpha() for c in t)
    }


def strip_repeating(text: str, repeating: set[str]) -> str:
    """Drop every line whose digit-masked form is in `repeating`; keep all other lines."""
    if not repeating:
        return text
    kept = [ln for ln in text.split("\n") if _template(ln) not in repeating]
    return "\n".join(kept)


def section_for(top_line: str) -> str | None:
    """Return the line if it is a GPO section title ('Section IV: ...'), else None."""
    line = top_line.strip()
    return line if _SECTION_RE.match(line) else None
