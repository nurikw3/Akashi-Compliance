from dataclasses import replace

from app.core.config import Settings, normalize_adata_individual_base_url
from app.services.adata import client as adata_client
from app.services.adata.client import _normalize_individual_court_case


def test_individual_court_urls_not_under_company_prefix():
    base = normalize_adata_individual_base_url("https://api.adata.kz/api/company")
    assert base == "https://api.adata.kz/api/individual"
    token = "test-token"
    assert (
        f"{base}/court-case/details/{token}"
        == "https://api.adata.kz/api/individual/court-case/details/test-token"
    )
    assert (
        f"{base}/info/check/{token}"
        == "https://api.adata.kz/api/individual/info/check/test-token"
    )


def test_client_individual_paths_use_individual_base(monkeypatch):
    patched = replace(
        adata_client.settings,
        adata_base_url="https://api.adata.kz/api/company",
        adata_token="test-token",
    )
    monkeypatch.setattr(adata_client, "settings", patched)
    assert (
        adata_client._individual_token_path("court-case/details")
        == "https://api.adata.kz/api/individual/court-case/details/test-token"
    )
    assert (
        adata_client._individual_info_check_url()
        == "https://api.adata.kz/api/individual/info/check/test-token"
    )


def test_normalize_individual_court_case_case_level_documents():
    raw = {
        "number": "1",
        "documents": [{"file_name": "a.pdf", "doc_link": "https://cdn.example/a.pdf"}],
        "history": [{"event_date": "2020-01-01", "name": "Старт"}],
        "sides": ["Иванов И.И."],
    }
    case = _normalize_individual_court_case(raw)
    assert case["documents"][0]["doc_link"] == "https://cdn.example/a.pdf"
    assert case["participants"] == ["Иванов И.И."]
    assert case["defendants"] == []
    assert len(case["history"]) == 1


def test_normalize_individual_preserves_role_over_sides():
    raw = {
        "number": "7528-23-00-3/41432",
        "role": "Третья сторона",
        "category": "Статья 73",
        "defendants": ["НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ", "ИВАНОВ И.И."],
    }
    case = _normalize_individual_court_case(raw)
    assert case["role"] == "Третья сторона"
    assert "НУРУШЕВ" in case["defendants"][0]
