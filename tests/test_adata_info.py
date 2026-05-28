from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.enrichment.mapper import company_data_to_enrichment
from app.services.enrichment.providers.adata import AdataProvider
from app.services.adata.client import run_parallel_checks

MOCK_INFO_DATA = {
    "name_ru": "ТОО «Тест Компания»",
    "director": "Иванов Иван Иванович",
    "company_status_name": "Действующее",
    "legal_address": "г. Алматы, ул. Абая 1",
    "registration_date": "2015-03-10",
    "employees": 42,
    "oked": "62.01",
    "tax_debt": 250_000,
    "sanction": False,
    "affiliation_by_company": [
        {
            "name": "ТОО Связанная",
            "bin": "123456789012",
            "bin_formatted": "123456789012",
            "type": "Дочерняя",
        }
    ],
    "courtcase": {
        "total_civil_count": 2,
        "total_criminal_count": 0,
        "total_administrative_count": 1,
        "total_appk_count": 0,
        "court_cases": [
            {
                "year": "2024",
                "civil_count": 2,
                "criminal_count": 0,
                "administrative_count": 1,
                "appk_count": 0,
            }
        ],
    },
}

MOCK_INFO_RESPONSE = {"success": True, "data": MOCK_INFO_DATA}


@pytest.mark.asyncio
async def test_fetch_company_info_primary_no_fallbacks_when_complete():
    with patch(
        "app.services.adata.client.fetch_company_info",
        new_callable=AsyncMock,
        return_value=MOCK_INFO_DATA,
    ) as fetch_info:
        with patch("app.services.adata.client._get_endpoint", new_callable=AsyncMock) as get_ep:
            result = await run_parallel_checks("123456789012")

    fetch_info.assert_awaited_once_with("123456789012")
    get_ep.assert_not_awaited()
    assert result["info"]["data"] == MOCK_INFO_DATA
    assert "basic" not in result
    assert "courtcase" not in result


@pytest.mark.asyncio
async def test_run_parallel_checks_fetches_courtcase_when_info_lacks_courts():
    sparse_info = {
        "name_ru": "ТОО Минимум",
        "tax_debt": 0,
        "sanction": False,
    }
    noop = AsyncMock(return_value={"success": True, "data": {}})
    with patch(
        "app.services.adata.client.fetch_company_info",
        new_callable=AsyncMock,
        return_value=sparse_info,
    ):
            with patch(
                "app.services.adata.client._fetch_fallback", new_callable=AsyncMock
            ) as fetch_fallback:
                async def _side_effect(_client, suffix, _bin):
                    if suffix == "courtcase":
                        return {"success": True, "data": {"total_civil_count": 1}}
                    return {"success": True, "data": {}}

                fetch_fallback.side_effect = _side_effect
                result = await run_parallel_checks("123456789012")

    court_calls = [c for c in fetch_fallback.await_args_list if c.args[1] == "courtcase"]
    assert len(court_calls) == 1
    assert "courtcase" in result
    assert result["info"]["data"]["name_ru"] == "ТОО Минимум"


def test_map_raw_from_info_payload():
    provider = AdataProvider()
    raw = {
        "info": MOCK_INFO_RESPONSE,
    }
    company = provider._map_raw("123456789012", raw, "")

    assert company.name == "ТОО «Тест Компания»"
    assert company.director == "Иванов Иван Иванович"
    assert company.status == "Действующее"
    assert company.address == "г. Алматы, ул. Абая 1"
    assert company.tax_debt == 250_000.0
    assert company.employees == 42
    assert company.industry == "62.01"
    assert company.in_sanctions_list is False
    assert company.court_cases == 3
    assert len(company.related_companies) == 1
    assert company.raw["info"] == MOCK_INFO_RESPONSE

    assert company.section_sources["companyInfo"] == "adata"
    assert company.section_sources["taxes"] == "adata"
    assert company.section_sources["courts"] == "adata"
    assert company.section_sources["sanctions"] == "adata"
    assert company.section_sources["affiliates"] == "adata"
    assert company.section_sources["assessment"] == "stub"


def test_company_data_enrichment_from_info():
    provider = AdataProvider()
    company = provider._map_raw("123456789012", {"info": MOCK_INFO_RESPONSE}, "Fallback")
    enrichment = company_data_to_enrichment(company.name or "Fallback", company)

    assert enrichment["companyInfo"]["fullName"] == "ТОО «Тест Компания»"
    assert enrichment["taxes"]["debt"] == 250_000
    assert enrichment["courts"]["activeCases"] == 3
    assert enrichment["sanctions"]["isOnList"] is False
    assert len(enrichment["affiliates"]["companies"]) == 1
