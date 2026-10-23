from app.ingestion.pdf_text import collect_repeating_lines, section_for, strip_repeating

SEC4 = "Section IV: Notes to the Financial Statements"
SEC1 = "Section I: Management Discussion and Analysis (Unaudited)"


def _pages(n: int, top: str, bottom: str = "") -> list[tuple[str, str]]:
    return [(top, bottom) for _ in range(n)]


def test_collect_detects_recurring_section_header():
    pages = _pages(20, SEC4, "")
    repeating = collect_repeating_lines(pages, min_recurrence=5)
    assert any("Section" in t and "Notes to the Financial Statements" in t for t in repeating)


def test_collect_masks_digits_in_templates():
    pages = [(f"Page {i}", "") for i in range(1, 11)]
    repeating = collect_repeating_lines(pages, min_recurrence=5)
    assert "Page #" in repeating


def test_collect_below_threshold_not_returned():
    pages = _pages(3, SEC1, "")
    assert collect_repeating_lines(pages, min_recurrence=5) == set()


def test_collect_excludes_numeric_only_templates():
    pages = _pages(20, "26", "2018")
    repeating = collect_repeating_lines(pages, min_recurrence=5)
    for t in repeating:
        assert any(c.isalpha() for c in t), f"numeric-only template leaked: {t!r}"
    assert "##" not in repeating
    assert "####" not in repeating


def test_strip_removes_running_header_and_keeps_prose():
    repeating = collect_repeating_lines(_pages(20, SEC4, ""), min_recurrence=5)
    body = (
        f"{SEC4}\n"
        "The Corporation recognised revenue under the new standard.\n"
        "Expenses rose by 12 percent year over year.\n"
    )
    out = strip_repeating(body, repeating)
    assert SEC4 not in out
    assert "The Corporation recognised revenue under the new standard." in out
    assert "Expenses rose by 12 percent year over year." in out


def test_strip_keeps_standalone_numeric_line():
    repeating = collect_repeating_lines(_pages(20, "26", "2018"), min_recurrence=5)
    text = "Intro paragraph.\n26\nMore prose.\n2018\nEnd."
    out = strip_repeating(text, repeating)
    assert "26" in out.splitlines()
    assert "2018" in out.splitlines()


def test_strip_empty_repeating_set_is_identity():
    text = f"{SEC4}\nSome prose."
    assert strip_repeating(text, set()) == text


def test_section_for_returns_section_title():
    assert section_for("Section I: Management Discussion and Analysis") == (
        "Section I: Management Discussion and Analysis"
    )
    assert section_for(SEC4) == SEC4


def test_section_for_ignores_prose():
    assert section_for("The GPO printed millions of documents") is None


def test_section_for_rejects_empty_title():
    assert section_for("Section IV:") is None
