"""Unit tests for the compact, plain-Russian sanctions summary + PDF + glossary.

Pure functions over a synthetic ``enriched_data`` dict — no DB, no network.
The LLM narrative is skipped automatically when OPENAI_API_KEY is unset
(``build_sanctions_summary`` stays deterministic).
"""
from __future__ import annotations

from app.services.reports import glossary
from app.services.reports.sanctions_pdf import render_sanctions_pdf
from app.services.reports.sanctions_summary import build_sanctions_summary


def _enriched_fixture() -> dict:
    sanctioned_hit = {
        "primaryName": "VK TEKHNOLOGII PAO",
        "submittedName": 'ПУБЛИЧНОЕ АО "ВК ТЕХНОЛОГИИ"',
        "matchStrength": "EXACT",
        "matchScore": 99.0,
        "sfResult": "NONE",
        "isSanction": True,
        "isPep": True,
        "sanctionLists": [
            "INTERNATIONAL - INSAE-50-OFAC-WC - Entity 50% owned [Implicit Sanctions]",
            "USA - BIS-WC - Bureau of Industry and Security",
            "State Invested Enterprise",
        ],
        "sanctioningCountries": ["United States", "European Union", "United Kingdom"],
        "identifications": [
            {"type": "RU-OGRN", "value": "1217700575355", "name": "Main State Registration Number", "issuingCountry": "Russian Federation"},
        ],
        "locationDetails": [
            {"type": "REGISTEREDIN", "countryName": "Russian Federation", "countryCode": "RUS", "region": None},
        ],
        "recordDates": {
            "INITIAL_PUBLISHED_DATE": "2025-11-06T10:20:36.948Z",
            "LAST_PUBLISHED_DATE": "2026-01-29T09:31:15.791Z",
        },
        "furtherInformation": [
            {"type": "SANCTION", "title": "SANCTIONS RELATED", "text": "Meets inclusion criteria for EU, OFAC and UKHMT."},
        ],
    }
    return {
        "lseg": {
            "screenedName": "BK TEX KAZAKHSTAN",
            "screenedIin": "220840001616",
            "screenedAt": "2026-06-12T00:12:00Z",
            "sanctions": {"hits": []},
            "pep": {"individuals": []},
        },
        "lsegExtended": {
            "vk": {"name": 'ПУБЛИЧНОЕ АО "ВК ТЕХНОЛОГИИ"', "role": "Учредитель", "hits": [sanctioned_hit]},
            "fp": {"name": 'ТОО "BK ТЕХ"', "role": "Аффилиат", "hits": [{
                "primaryName": "KAVEH CUTTING TOOLS COMPANY",
                "matchStrength": "MEDIUM", "matchScore": 86.0, "sfResult": "UNKNOWN",
                "isSanction": True, "sanctionLists": ["IRAN - X - Y"],
            }]},
            "clean": {"name": "СУХОБАЕВСКИЙ ИГОРЬ", "role": "Учредитель", "hits": []},
        },
    }


def test_false_positives_are_filtered_out() -> None:
    """EXACT match shown; MEDIUM+UNKNOWN (вероятный однофамилец) → hidden, not subjects."""
    summary = build_sanctions_summary(_enriched_fixture())
    assert summary["meta"]["subjectCount"] == 1                  # only the EXACT VK match
    assert summary["subjects"][0]["matchedName"] == "VK TEKHNOLOGII PAO"
    assert len(summary["hidden"]) == 1                           # KAVEH MEDIUM hidden
    assert summary["hidden"][0]["name"] == "KAVEH CUTTING TOOLS COMPANY"


def test_compact_skeleton_is_plain_russian() -> None:
    summary = build_sanctions_summary(_enriched_fixture())
    assert summary["meta"]["company"] == "BK TEX KAZAKHSTAN"
    assert summary["meta"]["subjectCount"] == 1
    assert summary["legend"]  # term explanations present

    s = summary["subjects"][0]
    assert s["country"] == "Russian Federation"
    assert "США" in s["whoImposed"]                       # collapsed jurisdictions
    assert any("правило 50%" in t for t in s["sanctionType"])  # decoded type
    assert s["when"] == "внесён 2025-11-06, обновлён 2026-01-29"
    assert s["reason"]                                    # plain fallback reason
    assert s["keyRefs"]                                   # OGRN surfaced
    assert len(summary["coverage"]) == 3


def test_glossary_decoders() -> None:
    assert "правило 50%" in " ".join(
        glossary.classify_sanction_type(["INSAE-50-OFAC-WC [Implicit Sanctions]"], [])
    )
    assert "прямые санкции" in glossary.classify_sanction_type(["USA - OFAC - SDN List"], [])
    assert "ещё" in glossary.collapse_jurisdictions(
        ["United States", "European Union", "United Kingdom", "United Nations", "Australia", "Japan"]
    )
    assert glossary.decode_keyword("INTERNATIONAL - RSSRE-50-WC - x") is not None
    assert "политик" in glossary.PEP_PLAIN


def test_render_pdf_valid() -> None:
    pdf = render_sanctions_pdf(build_sanctions_summary(_enriched_fixture()))
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 2000


def test_empty_enriched() -> None:
    summary = build_sanctions_summary({})
    assert summary["subjects"] == []
    assert render_sanctions_pdf(summary)[:4] == b"%PDF"
