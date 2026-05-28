"""Tests for unified Adata company/info payload (CORE 24/7 shape)."""

from __future__ import annotations

from app.services.adata.info_mapper import map_info_data
from app.services.enrichment.mapper import company_data_to_enrichment
from app.services.enrichment.providers.adata import AdataProvider
from app.services.enrichment.base import CompanyData

CORE_INFO_DATA = {
    "basic": {
        "name_ru": 'ТОВАРИЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "CORE 24/7"',
        "short_name": 'ТОО "CORE 24/7"',
        "biin": "171040021791",
        "legal_address": "город Алматы, Алмалинский район, улица Макатаева, дом, 117",
        "oked": "Разработка программного обеспечения",
        "employee_count": 15,
        "fullname_director": "УСПАНОВ РУСТЕМ КАЙРАТОВИЧ",
        "date_registration": "2017-10-16",
        "financial_problems": True,
    },
    "status": {
        "company_status": True,
        "tax_debt": 6033.19,
        "financial_problems": True,
        "violation_tax": False,
    },
    "riskFactor": {
        "company": {"bankrupt": False, "tax_risk_degree": "средняя"},
        "head": {
            "terrorist": False,
            "litigation": {
                "total_civil_count": 1,
                "total_criminal_count": 0,
                "total_administrative_count": 1,
                "total_appk_count": 0,
                "court_cases": [
                    {
                        "year": "2024",
                        "civil_count": 1,
                        "criminal_count": 0,
                        "administrative_count": 0,
                        "appk_count": 0,
                    },
                    {
                        "year": "2016",
                        "civil_count": 0,
                        "criminal_count": 0,
                        "administrative_count": 1,
                        "appk_count": 0,
                    },
                ],
            },
        },
    },
    "litigation": {
        "total_civil_count": 0,
        "court_cases": [],
    },
    "founders": {
        "founders_cnt": 3,
        "founders_dtl": [
            {"name": "КОНДРАТЬЕВ ИВАН АЛЕКСАНДРОВИЧ", "is_company": False},
            {"name": "УСПАНОВ РУСТЕМ КАЙРАТОВИЧ", "is_company": False},
        ],
    },
    "connectedDiagram": {
        "affiliation_by_head": {
            "head_name": "УСПАНОВ РУСТЕМ КАЙРАТОВИЧ",
            "companies": [
                {
                    "bin": "200940900060",
                    "type": "Учредитель",
                    "name": 'ЧАСТНАЯ КОМПАНИЯ 2R LTD.',
                    "bin_formatted": "200940900060",
                    "director": "УСПАНОВ РУСТЕМ КАЙРАТОВИЧ",
                },
            ],
        },
    },
}


def test_map_core_info_structure():
    mapped = map_info_data("171040021791", CORE_INFO_DATA)
    assert "Финансовые проблемы" in mapped["status_flags"]
    assert any("Налоговый риск" in f for f in mapped["risk_flags"])
    assert mapped["name"] == 'ТОО "CORE 24/7"'
    assert mapped["director"] == "УСПАНОВ РУСТЕМ КАЙРАТОВИЧ"
    assert mapped["tax_debt"] == 6033.19
    assert mapped["employees"] == 15
    assert mapped["status"] == "действующая"
    assert mapped["court_cases"] == 2
    assert mapped["raw"]["courts_scope"] == "director"
    assert len(mapped["related_companies"]) >= 1
    assert mapped["related_companies"][0]["iinBin"] == "200940900060"
    assert mapped["section_sources"]["companyInfo"] == "adata"
    assert mapped["section_sources"]["courts"] == "adata"


def test_provider_map_raw_core():
    provider = AdataProvider()
    raw = {"info": {"success": True, "data": CORE_INFO_DATA}}
    company = provider._map_raw("171040021791", raw, "")
    assert company.name == 'ТОО "CORE 24/7"'
    assert company.court_cases == 2
    enrichment = company_data_to_enrichment(company.name or "", company)
    assert enrichment["courts"]["activeCases"] == 2
    assert enrichment["courts"]["scope"] == "director"
    assert len(enrichment["courts"]["cases"]) == 2
    assert enrichment["affiliates"]["companies"][0]["name"] == 'ЧАСТНАЯ КОМПАНИЯ 2R LTD.'
