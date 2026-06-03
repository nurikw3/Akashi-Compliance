"""Company detailed court cases from info/check (paginated court_cases)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.adata import client as adata_client
from app.services.adata.client import (
    _is_aggregate_court_year_row,
    _is_detailed_court_case_row,
    _merge_company_info_court_pages,
    _normalize_individual_court_case,
)
from app.services.adata.info_mapper import _extract_detailed_company_court_cases, map_info_data

MOCK_DETAILED_CASE = {
    "number": "12345-2024",
    "type": "Гражданское дело",
    "sides": ["ТОО Тест", "Иванов И.И."],
    "date": "2024-01-15",
    "court": "Специализированный межрайонный суд",
    "category": "Взыскание",
    "role": "Третья сторона",
    "documents": [
        {"file_name": "решение.pdf", "doc_link": "https://cdn.adata.kz/doc/1"},
    ],
    "history": [{"event_date": "2024-01-10", "name": "Принято к производству"}],
}


def test_is_detailed_vs_aggregate_court_rows():
    assert _is_detailed_court_case_row(MOCK_DETAILED_CASE) is True
    assert _is_aggregate_court_year_row({"year": "2024", "civil_count": 2}) is True
    assert _is_detailed_court_case_row({"year": "2024", "civil_count": 2}) is False


def test_extract_detailed_company_court_cases_from_info():
    info_data = {
        "basic": {"short_name": "ТОО"},
        "court_cases": [MOCK_DETAILED_CASE],
        "current_page": 1,
        "last_page": 1,
        "total": 1,
    }
    cases = _extract_detailed_company_court_cases(info_data)
    assert len(cases) == 1
    assert cases[0]["number"] == "12345-2024"
    assert cases[0]["documents"][0]["doc_link"] == "https://cdn.adata.kz/doc/1"
    assert cases[0]["defendants"] == ["ТОО Тест", "Иванов И.И."]


def test_map_info_data_sets_company_court_cases_on_raw():
    info_data = {
        "basic": {"short_name": "ТОО Тест"},
        "litigation": {
            "total_civil_count": 1,
            "total_criminal_count": 0,
            "total_administrative_count": 0,
            "court_cases": [{"year": "2024", "civil_count": 1, "criminal_count": 0}],
        },
        "court_cases": [MOCK_DETAILED_CASE],
    }
    mapped = map_info_data("123456789012", info_data)
    detailed = mapped["raw"]["_company_court_cases"]
    assert len(detailed) == 1
    assert detailed[0]["number"] == "12345-2024"


@pytest.mark.asyncio
async def test_merge_company_info_court_pages_fetches_extra_pages():
    page1_case = {**MOCK_DETAILED_CASE, "number": "page-1"}
    page2_case = {**MOCK_DETAILED_CASE, "number": "page-2"}

    data = {
        "basic": {"short_name": "ТОО"},
        "court_cases": [page1_case],
        "current_page": 1,
        "last_page": 2,
        "total": 2,
        "per_page": 1,
    }

    page2_payload = {
        "success": True,
        "data": {"court_cases": [page2_case], "current_page": 2, "last_page": 2},
    }

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=page2_payload)

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    merged = await _merge_company_info_court_pages(mock_client, "job-token", data)
    assert len(merged["court_cases"]) == 2
    numbers = {c["number"] for c in merged["court_cases"]}
    assert numbers == {"page-1", "page-2"}
    mock_client.get.assert_awaited_once()
    call_kwargs = mock_client.get.await_args
    assert call_kwargs.kwargs["params"] == {"token": "job-token", "page": 2}


@pytest.mark.asyncio
async def test_merge_skips_when_only_aggregate_rows():
    data = {
        "litigation": {},
        "court_cases": [{"year": "2024", "civil_count": 1, "criminal_count": 0}],
        "last_page": 3,
    }
    mock_client = MagicMock()
    mock_client.get = AsyncMock()
    merged = await _merge_company_info_court_pages(mock_client, "job-token", data)
    assert merged["court_cases"] == data["court_cases"]
    mock_client.get.assert_not_awaited()


def test_normalize_matches_individual_shape():
    case = _normalize_individual_court_case(MOCK_DETAILED_CASE)
    assert case["role"] == "Третья сторона"
    assert case["history"][0]["name"] == "Принято к производству"
