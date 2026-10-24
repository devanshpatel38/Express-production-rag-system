"""Eval gold-set schema + harness wiring smoke (pipeline mocked)."""
import json
from types import SimpleNamespace

from eval import run_eval


def test_dataset_schema():
    items = run_eval._load_dataset()
    assert len(items) >= 12
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids))
    for it in items:
        assert it["question"].strip()
        assert it["ground_truth"].strip()
        pages = it["reference_pages"]
        assert isinstance(pages, list) and pages
        assert all(isinstance(p, int) and 1 <= p <= 12 for p in pages)


def test_harness_collect_and_hit_rate(monkeypatch):
    def fake_pipeline(query, history):
        cand = SimpleNamespace(text="ctx", page=10)
        return SimpleNamespace(answer="a", latency_ms=5, post_rerank=[cand])

    monkeypatch.setattr(run_eval, "run_pipeline", fake_pipeline)
    items = run_eval._load_dataset()[:2]
    rows = run_eval._run_pipeline_collect(items)
    assert len(rows) == 2 and rows[0]["contexts"] == ["ctx"]
    assert run_eval._retrieval_hit_rate(rows) == 1.0
    rows[0]["_retrieved_pages"] = [99]
    assert run_eval._retrieval_hit_rate(rows) == 0.5


def test_report_is_ascii(capsys):
    run_eval._print_report({"faithfulness": 0.1}, 0.5, 10)
    capsys.readouterr().out.encode("ascii")
