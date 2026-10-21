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
