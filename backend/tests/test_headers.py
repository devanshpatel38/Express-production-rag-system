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
