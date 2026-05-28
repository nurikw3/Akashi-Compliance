from app.services.enrichment.mapper import company_data_to_enrichment
from app.services.enrichment.base import CompanyData
from app.services.enrichment.providers.adata import AdataProvider
from app.services.enrichment.sources import infer_section_sources_from_data


MOCK_COURTCASE = {
    "success": True,
    "data": {
        "total_civil_count": 5,
        "total_criminal_count": 1,
        "total_administrative_count": 2,
        "total_appk_count": 0,
        "court_cases": [
            {
                "year": "2024",
                "civil_count": 3,
                "criminal_count": 0,
                "administrative_count": 1,
                "appk_count": 0,
            },
            {
                "year": "2023",
                "civil_count": 2,
                "criminal_count": 1,
                "administrative_count": 1,
                "appk_count": 0,
            },
        ],
    },
}


def test_parse_courtcase_maps_totals_and_years():
    provider = AdataProvider()
    active, years, totals, ui_cases = provider._parse_courtcase(MOCK_COURTCASE)

    assert active == 8
    assert totals["civil"] == 5
    assert len(years) == 2
    assert len(ui_cases) == 2
    assert ui_cases[0]["date"] == "2024"


def test_company_data_courts_enrichment_from_courtcase():
    provider = AdataProvider()
    active, years, totals, ui_cases = provider._parse_courtcase(MOCK_COURTCASE)
    data = CompanyData(
        iin="123456789012",
        court_cases=active,
        court_cases_years=years,
        court_totals=totals,
        raw={"courtcase": MOCK_COURTCASE, "_court_ui_cases": ui_cases, "_courts_source": "adata"},
    )
    data.section_sources = infer_section_sources_from_data(data, "adata")

    enrichment = company_data_to_enrichment("Test Co", data)
    assert enrichment["courts"]["activeCases"] == 8
    assert len(enrichment["courts"]["cases"]) == 2
    assert data.section_sources["courts"] == "adata"


def test_courtcase_failure_marks_stub():
    data = CompanyData(
        iin="123456789012",
        court_cases=2,
        raw={"courtcase": {"error": "timeout"}, "_courts_source": "stub"},
    )
    sources = infer_section_sources_from_data(data, "adata")
    assert sources["courts"] == "stub"
