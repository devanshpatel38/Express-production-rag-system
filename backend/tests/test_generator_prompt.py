from app.rag.generator import SYSTEM_PROMPT, _format_context
from app.rag.retriever import Candidate


def _cand(**overrides) -> Candidate:
    base = dict(
        chunk_id="x",
        text="4.0",
        source_path="GEP-Jun-2026.pdf",
        title="t",
        section="EMDE growth",
        score=1.0,
        page=100,
        units="percent",
        chunk_type="table_row",
    )
    base.update(overrides)
    return Candidate(**base)


def test_context_block_shows_page_and_units():
    c = _cand()
    out = _format_context([c])
    assert "p100" in out and "percent" in out


def test_context_block_omits_page_when_none():
    out = _format_context([_cand(page=None)])
    assert "p100" not in out
    assert "(percent)" in out
    assert out.startswith("[#1] EMDE growth")


def test_context_block_omits_units_when_empty():
    out = _format_context([_cand(units="")])
    assert "p100" in out
    assert "percent" not in out
    assert "EMDE growth (p100)" in out


def test_context_block_keeps_numbering_and_body():
    out = _format_context([_cand(), _cand(section="Other", page=None, units="")])
    assert out.startswith("[#1] EMDE growth (p100, percent)\n4.0")
    assert "[#2] Other\n4.0" in out


def test_system_prompt_forbids_guessing():
    assert "never" in SYSTEM_PROMPT.lower() and "context" in SYSTEM_PROMPT.lower()
    lowered = SYSTEM_PROMPT.lower()
    assert "never guess" in lowered
    assert "units" in lowered and "reference period" in lowered
    assert "[#1]" in SYSTEM_PROMPT
