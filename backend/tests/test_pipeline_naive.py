from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.rag import pipeline


def _cand(i: int):
    return SimpleNamespace(
        chunk_id=f"c{i}", text=f"text {i}", source_path="doc.pdf", title="Doc",
        section="", score=1.0 - i * 0.1, page=i + 1, units="kWh", chunk_type="table",
    )


class _FakeRetriever:
    def retrieve(self, query):
        return [_cand(i) for i in range(3)]


class _FakeReranker:
    enabled = True

    def rerank(self, query, candidates, k):
        return candidates[:k]


class _FakeGenerator:
    def generate(self, query, candidates, history):
        return "fixed"


def test_run_pipeline_straight_path(monkeypatch):
    monkeypatch.setattr(pipeline, "get_retriever", lambda: _FakeRetriever())
    monkeypatch.setattr(pipeline, "get_reranker", lambda: _FakeReranker())
    monkeypatch.setattr(pipeline, "get_generator", lambda: _FakeGenerator())

    result = pipeline.run_pipeline("q")
    assert result.answer == "fixed"
    assert len(result.post_rerank) <= get_settings().top_k_rerank
    assert result.sources[0].page == 1
    assert result.sources[0].units == "kWh"
    assert result.sources[0].chunk_type == "table"


def test_self_healing_modules_removed():
    with pytest.raises(ModuleNotFoundError):
        import app.rag.cache  # noqa: F401
