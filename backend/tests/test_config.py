from app.config import get_settings


def test_gpo_settings():
    s = get_settings.__wrapped__()
    assert s.collection_name == "gpo_report"
    assert s.source_pdf_path.endswith("GPO-Anual-report.pdf")
    assert s.top_k_rerank == 10
    assert s.header_footer_min_recurrence == 8
    assert s.app_name == "gpo-report-rag"
    assert s.chroma_path == "./data/chroma"
    assert not hasattr(s, "self_healing_enabled")
    assert not hasattr(s, "semantic_cache_enabled")
