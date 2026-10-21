from app.ingestion.pdf_text import collect_repeating_lines, strip_repeating


def test_detects_and_strips_running_header():
    pages = []
    for i in range(20):
        top = f"CHAPTER {i % 3} \nGLOBAL ECONOMIC PROSPECTS | JUNE 2026 \n{40 + i}"
        pages.append((top, ""))
    repeating = collect_repeating_lines(pages, min_recurrence=10)
    assert "CHAPTER # \nGLOBAL ECONOMIC PROSPECTS | JUNE #### \n##" in repeating

    body = (
        "CHAPTER 1 \nGLOBAL ECONOMIC PROSPECTS | JUNE 2026 \n45\n"
        "Real prose about the economy stays put."
    )
    stripped = strip_repeating(body, repeating)
    assert "GLOBAL ECONOMIC PROSPECTS" not in stripped
    assert "Real prose about the economy stays put." in stripped


def test_numeric_body_lines_survive_strip():
    # A bare page number recurs on every page and masks to "##", so it is in
    # the repeating set. Numeric-only templates must not strip body lines.
    pages = [("", str(40 + i)) for i in range(20)]
    repeating = collect_repeating_lines(pages, min_recurrence=10)
    assert "##" in repeating

    body = "Table value\n12\nSource note\n2019\nMore prose."
    stripped = strip_repeating(body, repeating)
    assert stripped.split("\n") == ["Table value", "12", "Source note", "2019", "More prose."]


def test_full_running_header_removed_including_page_number():
    pages = [("CHAPTER 1 \nGLOBAL ECONOMIC PROSPECTS | JUNE 2026 \n" + str(40 + i), "")
             for i in range(20)]
    repeating = collect_repeating_lines(pages, min_recurrence=10)
    body = "CHAPTER 2 \nGLOBAL ECONOMIC PROSPECTS | JUNE 2026 \n57\nKept line\n12"
    assert strip_repeating(body, repeating).split("\n") == ["Kept line", "12"]
