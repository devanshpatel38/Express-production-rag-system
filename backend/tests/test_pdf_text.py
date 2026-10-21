from app.ingestion.pdf_text import normalize_text


def test_dehyphenate_linebreak():
    assert normalize_text("inter-\nvention") == "intervention"


def test_collapse_whitespace():
    # paragraph breaks preserved, inline runs collapsed
    assert normalize_text("a   b\n\n c") == "a b\n\nc"


def test_repair_replacement_char():
    # the Ghostscript artifact for a curly quote becomes a straight quote
    assert "�" not in normalize_text("Intervening �against� the Fed")
    assert normalize_text("Intervening �against� the Fed") == 'Intervening "against" the Fed'


def test_repair_mojibake_quotes():
    assert normalize_text("the Fedâ\u0080\u0099s view") == "the Fed's view"


def test_mojibake_dash_at_line_end_does_not_fuse():
    # em dash (UTF-8 bytes decoded as cp1252) at a line end must not join the words
    result = normalize_text("word\u00e2\u0080\u0094\nword")
    assert "wordword" not in result
    assert "\n" not in result


def test_fffd_between_letters_is_apostrophe():
    assert normalize_text("Fed\ufffds") == "Fed's"


def test_digit_guard_keeps_numeric_range():
    # hyphen kept, no join; the line break collapses to a space
    assert normalize_text("2019-\n2020") == "2019- 2020"


def test_dehyphenate_tolerates_indented_continuation():
    assert normalize_text("inter-\n   vention") == "intervention"
