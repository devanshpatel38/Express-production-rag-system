import json

from eval.run_eval import EVAL_FILE, _retrieval_hit_rate


def test_dataset_and_hitrate_shape():
    items = json.loads(EVAL_FILE.read_text(encoding="utf-8"))["items"]
    assert items
    for it in items:
        pages = it["reference_pages"]
        assert isinstance(pages, list) and pages
        assert all(isinstance(p, int) and p >= 1 for p in pages)
        assert it["question"] and it["ground_truth"] and it["id"]
    hit = [{"_reference_pages": [81], "_retrieved_pages": [80, 81]}]
    miss = [{"_reference_pages": [81], "_retrieved_pages": [3, 4]}]
    assert _retrieval_hit_rate(hit) == 1.0
    assert _retrieval_hit_rate(miss) == 0.0
