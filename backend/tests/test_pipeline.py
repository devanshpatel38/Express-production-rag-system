"""Straight pipeline + reranker field preservation."""
from dataclasses import dataclass
from types import SimpleNamespace

from app.rag import pipeline, reranker
from app.rag.retriever import Candidate


@dataclass
class RichCandidate(Candidate):
    page: int = 0
    units: str = ""
    chunk_type: str = "text"


def _rich(i: int) -> RichCandidate:
    return RichCandidate(
        chunk_id=f"c{i}", text=f"t{i}", source_path="a.pdf", title="T", section="S",
        score=0.1, page=i, units="mm", chunk_type="table",
    )


def test_cohere_reranker_preserves_all_fields():
    r = reranker._CohereReranker.__new__(reranker._CohereReranker)
    r._model = "m"
    results = [SimpleNamespace(index=1, relevance_score=0.9), SimpleNamespace(index=0, relevance_score=0.4)]
    r._client = SimpleNamespace(rerank=lambda **kw: SimpleNamespace(results=results))
    out = r.rerank("q", [_rich(0), _rich(1)], 2)
    assert [c.chunk_id for c in out] == ["c1", "c0"]
    for c, score in zip(out, (0.9, 0.4)):
        n = int(c.chunk_id[1])
        assert isinstance(c, RichCandidate)
        assert (c.page, c.units, c.chunk_type) == (n, "mm", "table")
        assert c.score == score
        assert (c.text, c.title, c.section, c.source_path) == (f"t{n}", "T", "S", "a.pdf")


def test_run_pipeline_returns_answer_and_sources_no_trace(monkeypatch):
    cands = [_rich(0), _rich(1)]
    monkeypatch.setattr(pipeline, "get_retriever", lambda: SimpleNamespace(retrieve=lambda q: cands))
    monkeypatch.setattr(
        pipeline, "get_reranker",
        lambda: SimpleNamespace(enabled=True, rerank=lambda q, c, k: c[:k]),
    )
    monkeypatch.setattr(pipeline, "get_generator", lambda: SimpleNamespace(generate=lambda q, c, h: "ans"))
    res = pipeline.run_pipeline("q", [], top_k=1, use_reranker=True)
    assert res.answer == "ans"
    assert [s.chunk_id for s in res.sources] == ["c0"]
    assert not hasattr(res, "trace")


def test_app_main_imports():
    import app.main  # noqa: F401
