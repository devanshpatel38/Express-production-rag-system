from app.config import get_settings


def test_gep_settings():
    s = get_settings.__wrapped__()  # bypass lru_cache
    assert s.collection_name == "gep_report"
    assert s.source_pdf_path.endswith("GEP-Jun-2026.pdf")
    assert not hasattr(s, "self_healing_enabled")
    assert not hasattr(s, "semantic_cache_enabled")
