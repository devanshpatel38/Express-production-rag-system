import dataclasses
import importlib
import sys
import types
from dataclasses import dataclass

import pytest

from app.rag import pipeline, reranker as reranker_mod
from app.rag.retriever import Candidate


@dataclass
class FakeCand(Candidate):
    page: int | None = None
    units: str = ""
    chunk_type: str = "prose"


def _cand(i=1, **kw):
    return FakeCand(chunk_id=f"c{i}", text="hello world", source_path="a.pdf",
                    title="T", section="S", score=0.5, **kw)


class _Ret:
    def retrieve(self, q):
        return [_cand(1, page=7, units="kWh", chunk_type="table"), _cand(2)]


class _Rr:
    enabled = False


class _Gen:
    def generate(self, q, cands, history):
        return "ans"


def test_straight_pipeline_carries_page(monkeypatch):
    monkeypatch.setattr(pipeline, "get_retriever", lambda: _Ret())
    monkeypatch.setattr(pipeline, "get_reranker", lambda: _Rr())
    monkeypatch.setattr(pipeline, "get_generator", lambda: _Gen())
    r = pipeline.run_pipeline("q", top_k=1)
    assert r.answer == "ans"
    assert len(r.sources) == 1
    assert r.sources[0].page == 7
    assert r.sources[0].units == "kWh"
    assert r.sources[0].chunk_type == "table"


@pytest.mark.parametrize("m", ["cache", "router", "grader", "query_rewriter", "verifier"])
def test_removed_modules(m):
    sys.modules.pop(f"app.rag.{m}", None)
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"app.rag.{m}")


def test_cohere_reranker_preserves_fields():
    class Client:
        def rerank(self, model, query, documents, top_n):
            res = [types.SimpleNamespace(index=1, relevance_score=0.9)]
            return types.SimpleNamespace(results=res)

    rr = reranker_mod._CohereReranker.__new__(reranker_mod._CohereReranker)
    rr._client, rr._model = Client(), "m"
    cands = [_cand(1), _cand(2, page=3, units="MW", chunk_type="table")]
    out = rr.rerank("q", cands, 1)
    assert out[0].chunk_id == "c2"
    assert (out[0].page, out[0].units, out[0].chunk_type) == (3, "MW", "table")
    assert out[0].score == 0.9
