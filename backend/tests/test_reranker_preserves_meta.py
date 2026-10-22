"""Regression: the Cohere reranker must preserve Candidate metadata.

The reranker rebuilds the top-k after scoring. An earlier version constructed
Candidate by hand and silently dropped page/units/chunk_type (added later),
so the API returned null page/units on reranked sources. These tests pin the
fields through both reranker paths.
"""
from app.rag.retriever import Candidate
from app.rag.reranker import _CohereReranker, _PassthroughReranker


def _cand(i: int) -> Candidate:
    return Candidate(
        chunk_id=f"c{i}",
        text=f"text {i}",
        source_path="GEP-Jun-2026.pdf",
        title="TABLE 2.11",
        section="SSA",
        score=0.5,
        page=100 + i,
        units="percent",
        chunk_type="table_row",
    )


class _FakeResult:
    def __init__(self, index: int, score: float) -> None:
        self.index = index
        self.relevance_score = score


class _FakeResp:
    def __init__(self, results):
        self.results = results


class _FakeClient:
    def rerank(self, model, query, documents, top_n):
        # Return a different order than input to prove index mapping is used.
        n = min(top_n, len(documents))
        order = list(reversed(range(n)))
        return _FakeResp([_FakeResult(idx, 1.0 - 0.1 * rank) for rank, idx in enumerate(order)])


def test_cohere_rerank_preserves_metadata():
    rr = _CohereReranker.__new__(_CohereReranker)  # bypass cohere import/client init
    rr._client = _FakeClient()
    rr._model = "rerank-english-v3.0"

    cands = [_cand(0), _cand(1), _cand(2)]
    out = rr.rerank("q", cands, top_k=3)

    assert len(out) == 3
    # Metadata survives the rebuild for every reranked candidate.
    for o in out:
        assert o.page is not None
        assert o.units == "percent"
        assert o.chunk_type == "table_row"
    # Index mapping is correct: first result maps to input index 2 (page 102).
    assert out[0].page == 102
    # Score is overwritten with the rerank relevance.
    assert out[0].score == 1.0


def test_passthrough_rerank_preserves_metadata():
    pt = _PassthroughReranker()
    out = pt.rerank("q", [_cand(5)], top_k=1)
    assert out[0].page == 105
    assert out[0].units == "percent"
    assert out[0].chunk_type == "table_row"
