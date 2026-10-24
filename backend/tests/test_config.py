"""Config defaults for the iMac PER pipeline and removal of self-healing settings."""
import pytest

from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Ensure a developer's .env / shell env cannot change the defaults under test.
    monkeypatch.delenv("SOURCE_PDF_PATH", raising=False)
    monkeypatch.delenv("TOP_K_RERANK", raising=False)
    monkeypatch.delenv("COLLECTION_NAME", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_settings_loads():
    settings = get_settings()
    assert isinstance(settings, Settings)


def test_collection_name_is_imac_report():
    assert get_settings().collection_name == "imac_report"


def test_source_pdf_path_default():
    assert get_settings().source_pdf_path == "../iMac_PER_Oct2024.pdf"


def test_top_k_rerank_default_is_10():
    assert get_settings().top_k_rerank == 10


def test_storage_paths_kept():
    settings = get_settings()
    assert settings.chroma_path == "./data/chroma"
    assert settings.bm25_index_path == "./data/bm25.pkl"
    assert settings.docs_meta_path == "./data/docs_meta.json"


@pytest.mark.parametrize(
    "name",
    [
        "self_healing_enabled",
        "adaptive_routing_enabled",
        "hyde_enabled",
        "retrieval_grading_enabled",
        "faithfulness_check_enabled",
        "max_healing_attempts",
        "semantic_cache_enabled",
        "semantic_cache_threshold",
        "semantic_cache_size",
    ],
)
def test_self_healing_settings_removed(name):
    assert not hasattr(get_settings(), name)
