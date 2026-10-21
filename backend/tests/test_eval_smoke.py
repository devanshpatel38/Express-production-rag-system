import json

from eval.run_eval import EVAL_FILE, _retrieval_hit_rate


def test_dataset_and_hitrate_shape():
    items = json.loads(EVAL_FILE.read_text(encoding="utf-8"))["items"]
    assert items
    for it in items:
        refs = it["reference_pages"]
        assert isinstance(refs, list) and refs
        assert all(isinstance(p, int) and not isinstance(p, bool) for p in refs)

    hit = {"_reference_pages": [101], "_retrieved_pages": [3, 101]}
    miss = {"_reference_pages": [101], "_retrieved_pages": [3, 4]}
    assert _retrieval_hit_rate([hit]) == 1.0
    assert _retrieval_hit_rate([miss]) == 0.0
    assert _retrieval_hit_rate([hit, miss]) == 0.5


def test_skip_vision_items_filter():
    from eval.run_eval import _filter_items

    items = [{"id": "a"}, {"id": "b", "requires_vision": True}, {"id": "c", "requires_vision": False}]
    assert [i["id"] for i in _filter_items(items, True)] == ["a", "c"]
    assert [i["id"] for i in _filter_items(items, False)] == ["a", "b", "c"]
