import json
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import normalize_adata_courtcase_base_url
from app.services.adata import client as adata_client
from app.services.adata.client import _fallbacks_for_info, fetch_company_court_cases
from app.services.adata.info_mapper import map_info_data
from app.services.enrichment.providers.adata import AdataProvider


def test_courtcase_urls_not_under_company_prefix():
    base = normalize_adata_courtcase_base_url("https://api.adata.kz/api/company")
    assert base == "https://api.adata.kz/api/courtcase"
    token = "test-token"
    assert (
        f"{base}/{token}"
        == "https://api.adata.kz/api/courtcase/test-token"
    )


def test_client_courtcase_path_uses_courtcase_base(monkeypatch):
    patched = replace(
        adata_client.settings,
        adata_base_url="https://api.adata.kz/api/company",
        adata_token="test-token",
    )
    monkeypatch.setattr(adata_client, "settings", patched)
    assert (
        adata_client._courtcase_token_path()
        == "https://api.adata.kz/api/courtcase/test-token"
    )


def test_fallbacks_for_info_requests_courtcase_when_counts_zero_despite_court_cases_array():
    info_data = {
        "basic": {"short_name": "ТОО"},
        "litigation": {
            "court_cases": [{"year": "2025", "civil_count": 0, "criminal_count": 0}],
            "total_civil_count": 0,
            "total_criminal_count": 0,
            "total_administrative_count": 0,
        },
        "status": {},
        "connectedDiagram": {},
    }
    fallbacks = _fallbacks_for_info(info_data)
    assert "courtcase" in fallbacks


def test_map_info_data_merges_raw_courtcase_when_litigation_empty():
    info_data = {
        "basic": {"short_name": "ТОО Тест"},
        "litigation": {
            "court_cases": [{"year": "2025", "civil_count": 0, "criminal_count": 0}],
            "total_civil_count": 0,
            "total_criminal_count": 0,
            "total_administrative_count": 0,
        },
        "riskFactor": {
            "head": {
                "litigation": {
                    "total_civil_count": 2,
                    "total_criminal_count": 0,
                    "total_administrative_count": 0,
                }
            }
        },
    }
    raw = {
        "info": {"success": True, "data": info_data},
        "courtcase": {
            "success": True,
            "data": {
                "total_civil_count": 3,
                "total_criminal_count": 1,
                "total_administrative_count": 0,
                "court_cases": [
                    {
                        "year": "2024",
                        "civil_count": 3,
                        "criminal_count": 1,
                        "administrative_count": 0,
                    }
                ],
            },
        },
    }
    mapped = map_info_data("123456789012", info_data, raw=raw)
    assert mapped["court_cases"] == 4
    assert mapped["raw"]["courts_scope"] == "company"
    assert mapped["section_sources"]["courts"] == "adata"

    provider = AdataProvider()
    company = provider._map_raw("123456789012", raw, "")
    assert company.court_cases == 4
    assert company.raw.get("courts_scope") == "company"


MOCK_COURTCASE_DETAILED = {
    "success": True,
    "data": {
        "current_page": 1,
        "last_page": 1,
        "total": 2,
        "per_page": 10,
        "court_cases": [
            {
                "number": "7517-21-00-2/6609",
                "type": "Гражданское дело",
                "sides": ["ТОО 'ИТ-ГРАД'", "ТУСУПОВ ДАРХАН"],
                "date": "2021-12-14",
                "court": "Медеуский районный суд",
                "category": "ТРУДОВЫЕ СПОРЫ",
                "role": "Третья сторона",
                "status": "Дело не определено",
                "documents": [],
                "history": [],
            },
            {
                "number": "7599-22-00-2а/1489",
                "type": "Гражданское дело",
                "sides": ["ТУСУПОВ", 'ТОО "ИТ-ГРАД"'],
                "date": "2022-01-01",
                "court": "Алматинский городской суд",
                "category": "ТРУДОВЫЕ СПОРЫ",
                "role": "Ответчик",
                "status": "Дело закрыто",
                "result": "Дело выиграно",
                "documents": [
                    {"file_name": "doc1.pdf", "doc_link": "https://cdn.adata.kz/files/sud/doc1.pdf"},
                ],
                "history": [
                    {"event_date": "2022-02-03", "name": "Начало дела"},
                    {"event_date": "2022-04-04", "name": "Завершение дела"},
                ],
            },
        ],
    },
}


class _FakeResponse:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


@pytest.mark.asyncio
async def test_fetch_company_court_cases_returns_detailed_cases(monkeypatch):
    patched = replace(
        adata_client.settings,
        adata_base_url="https://api.adata.kz/api/company",
        adata_token="tok",
    )
    monkeypatch.setattr(adata_client, "settings", patched)

    with patch("app.services.adata.client.get_cached", new_callable=AsyncMock, return_value=None):
        with patch("app.services.adata.client.set_cached", new_callable=AsyncMock):
            init_resp = _FakeResponse({"success": True, "token": "job123"})
            poll_resp = _FakeResponse(MOCK_COURTCASE_DETAILED)

            async def _fake_get(url, params=None, **kw):
                if "courtcase" in url:
                    return init_resp
                return poll_resp

            fake_client = AsyncMock()
            fake_client.get = AsyncMock(side_effect=_fake_get)
            fake_client.__aenter__ = AsyncMock(return_value=fake_client)
            fake_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=fake_client):
                cases = await fetch_company_court_cases("150940013152")

    assert len(cases) == 2
    assert cases[0]["number"] == "7517-21-00-2/6609"
    assert cases[0]["role"] == "Третья сторона"
    assert cases[1]["number"] == "7599-22-00-2а/1489"
    assert len(cases[1]["documents"]) == 1
    assert cases[1]["documents"][0]["doc_link"] == "https://cdn.adata.kz/files/sud/doc1.pdf"
    assert len(cases[1]["history"]) == 2
