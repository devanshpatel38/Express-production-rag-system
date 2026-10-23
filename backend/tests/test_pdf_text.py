from app.ingestion.pdf_text import normalize_text


def test_letter_spaced_words_collapse_with_wide_gap():
    assert normalize_text("A N N U A L  R E P O R T") == "ANNUAL REPORT"


def test_dotted_initialism_and_spaced_word():
    assert normalize_text("U . S . G O V E R N M E N T") == "U.S. GOVERNMENT"


def test_pipe_separates_spaced_runs():
    s = "U . S . G O V E R N M E N T P U B L I S H I N G | 2 0 1 8 A N N U A L"
    # Known v1 limitation: single-spaced inter-word boundaries inside a run are lost.
    assert normalize_text(s) == "U.S. GOVERNMENTPUBLISHING | 2018 ANNUAL"


def test_dehyphenate_line_break():
    assert normalize_text("inter-\nvention") == "intervention"


def test_dehyphenate_digit_guarded():
    out = normalize_text("2018-\n2017")
    assert "2018" in out and "2017" in out
    assert "20182017" not in out


def test_whitespace_collapse_preserves_paragraphs():
    assert normalize_text("a   b\n\n c") == "a b\n\nc"


def test_mojibake_repair():
    assert normalize_text("it\u00e2\u20ac\u2122s") == "it\u2019s"
    assert "\ufffd" not in normalize_text("bad\ufffdchar")


def test_prose_unchanged():
    for s in [
        "The GPO printed millions of documents",
        "I am a U.S. citizen and a GPO employee.",
        "Plan A or B is fine, as is option C.",
        "He said a b test is not a spaced word.",
    ]:
        assert normalize_text(s) == s


def test_short_single_letter_sequence_untouched():
    assert normalize_text("see Part A B") == "see Part A B"
    assert normalize_text("x y") == "x y"


def test_lowercase_and_short_sequences_unchanged():
    assert normalize_text("a b c") == "a b c"
    assert normalize_text("I a m") == "I a m"
    assert normalize_text("Type I I I") == "Type I I I"
    assert normalize_text("see Part A B C") == "see Part A B C"


def test_trailing_punctuation_tolerated():
    assert normalize_text("R E P O R T.") == "REPORT."
    assert normalize_text("2 0 1 8.") == "2018."
