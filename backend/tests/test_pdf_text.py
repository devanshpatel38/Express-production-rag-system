from app.ingestion.pdf_text import (
    detect_running_header,
    normalize_text,
    strip_running_headers,
)


def test_mojibake_and_nbsp_repaired():
    raw = "Appleâ€™s iMac uses recycled aluminum—it’s great."
    assert normalize_text(raw) == "Apple's iMac uses recycled aluminum-it's great."


def test_generic_mojibake_repair():
    assert normalize_text("CafÃ©") == "Café"


def test_dehyphenate_letters_only():
    assert normalize_text("foot-\nprint") == "footprint"
    assert normalize_text("2024-\n25") == "2024-25"


def test_whitespace_collapsed_paragraphs_preserved():
    out = normalize_text("one   two \t three\n\n\n\nfour    five")
    assert out == "one two three\n\nfour five"


def _pages():
    words = "alpha beta gamma delta epsilon zeta eta".split()
    return [
        f"iMac | Product Environmental Report {n}\nUnique body text {w}.\n346"
        for n, w in enumerate(words, 1)
    ]


def test_running_header_detected_and_removed():
    pages = _pages()
    cleaned, header = strip_running_headers(pages)
    assert header == "iMac | Product Environmental Report #"
    assert detect_running_header(pages) == header
    assert all("Product Environmental Report" not in p for p in cleaned)
    assert all("Unique body text" in p for p in cleaned)


def test_numeric_only_line_not_removed():
    cleaned, _ = strip_running_headers(_pages())
    assert all("346" in p.splitlines() for p in cleaned)


def test_no_header_returns_none():
    cleaned, header = strip_running_headers(["a\n1", "b\n2"])
    assert header is None and cleaned == ["a\n1", "b\n2"]
