from app.rag.generator import SYSTEM_PROMPT, _format_context
from app.rag.retriever import Candidate


def _candidate(**overrides) -> Candidate:
    base = dict(
        chunk_id="c1",
        text="Total net sales were 1,234.",
        source_path="gpo-2018-annual-report.pdf",
        title="GPO 2018 Annual Report",
        section="Financial Highlights",
        score=0.9,
        page=80,
        units="dollars in thousands",
        chunk_type="table",
    )
    base.update(overrides)
    return Candidate(**base)


def test_context_block_shows_page_and_units():
    out = _format_context([_candidate(page=80, units="dollars in thousands")])
    assert "p80" in out
    assert "dollars in thousands" in out
    assert out.startswith("[#1] Financial Highlights (p80, dollars in thousands)")


def test_context_block_omits_page_when_none():
    out = _format_context([_candidate(page=None, units="dollars in thousands")])
    assert "(p" not in out
    assert out.startswith("[#1] Financial Highlights (dollars in thousands)")
    assert "Total net sales were 1,234." in out


def test_context_block_omits_units_when_empty():
    out = _format_context([_candidate(page=12, units="")])
    assert out.startswith("[#1] Financial Highlights (p12)")


def test_context_block_omits_both_when_absent():
    out = _format_context([_candidate(page=None, units="")])
    assert out.startswith("[#1] Financial Highlights\n")
    assert "()" not in out


def test_context_numbering_is_sequential():
    out = _format_context([_candidate(chunk_id="a", page=1), _candidate(chunk_id="b", page=2)])
    assert "[#1]" in out and "[#2]" in out


def test_system_prompt_forbids_guessing():
    lowered = SYSTEM_PROMPT.lower()
    assert "never" in lowered
    assert "context" in lowered
    assert "guess" in lowered


def test_system_prompt_names_report_and_requires_units_and_year():
    lowered = SYSTEM_PROMPT.lower()
    assert "gpo" in lowered
    assert "2018" in lowered
    assert "units" in lowered
    assert "[#n]" in SYSTEM_PROMPT
