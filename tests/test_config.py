from app.core.config import (
    normalize_adata_base_url,
    normalize_adata_courtcase_base_url,
    normalize_adata_individual_base_url,
)


def test_normalize_adata_base_url_appends_company_after_api():
    assert (
        normalize_adata_base_url("https://api.adata.kz/api")
        == "https://api.adata.kz/api/company"
    )


def test_normalize_adata_base_url_keeps_full_company_path():
    assert (
        normalize_adata_base_url("https://api.adata.kz/api/company")
        == "https://api.adata.kz/api/company"
    )


def test_normalize_adata_base_url_from_host_only():
    assert (
        normalize_adata_base_url("https://api.adata.kz")
        == "https://api.adata.kz/api/company"
    )


def test_normalize_adata_individual_base_url_from_company():
    assert (
        normalize_adata_individual_base_url("https://api.adata.kz/api/company")
        == "https://api.adata.kz/api/individual"
    )


def test_normalize_adata_courtcase_base_url_from_company():
    assert (
        normalize_adata_courtcase_base_url("https://api.adata.kz/api/company")
        == "https://api.adata.kz/api/courtcase"
    )
