from app.services.adata.info_mapper import map_info_data
from app.services.enrichment.mapper import company_data_to_enrichment
from app.services.enrichment.base import CompanyData
from app.services.risk.scoring import RiskScorer
from tests.test_adata_info_mapper import CORE_INFO_DATA


def _enrichment_for_core() -> dict:
    mapped = map_info_data("171040021791", CORE_INFO_DATA)
    fields = {k: mapped[k] for k in CompanyData.model_fields if k in mapped}
    company = CompanyData(**fields)
    company.raw = mapped.get("raw") or {}
    company.section_sources = mapped.get("section_sources") or {}
    return company_data_to_enrichment('ТОО "CORE 24/7"', company)


def test_tax_risk_does_not_set_sanctions_list() -> None:
    mapped = map_info_data("171040021791", CORE_INFO_DATA)
    assert any("Налоговый риск" in f for f in mapped["risk_flags"])
    assert mapped["in_sanctions_list"] is False


def test_sanctions_metric_zero_when_lseg_clean() -> None:
    enrichment = _enrichment_for_core()
    lseg = {
        "screenedAt": "2026-06-01T00:00:00+00:00",
        "screenedName": 'ТОО "CORE 24/7"',
        "sanctions": {
            "isOnList": False,
            "isFormalSanction": False,
            "hasWatchlistHits": False,
            "matchedLists": [],
            "hits": [
                {
                    "primaryName": "CORE CONSULTING",
                    "isSanction": False,
                    "isMaterialMatch": False,
                    "matchScore": 87,
                    "matchStrength": "MEDIUM",
                }
            ],
        },
    }
    result = RiskScorer().calculate(enrichment, lseg)
    sanctions = next(m for m in result.breakdown if m.metric == "sanctions")
    assert sanctions.points == 0
    assert "LSEG" in sanctions.reason
    assert "налоговый риск" not in sanctions.reason.lower()


def test_tax_risk_goes_to_taxes_metric() -> None:
    enrichment = _enrichment_for_core()
    result = RiskScorer().calculate(enrichment, None)
    taxes = next(m for m in result.breakdown if m.metric == "taxes")
    assert taxes.points > 0
    assert "Налоговый риск" in taxes.reason
