"""Unit tests for the full-dossier builder + PDF (no DB, no network)."""
from __future__ import annotations

import asyncio

from app.services.reports.dossier_pdf import render_dossier_pdf
from app.services.reports.dossier_summary import _money, build_dossier


def _enriched() -> dict:
    return {
        "iin": "220840001616",
        "lseg": {"screenedName": "BK TEX KAZAKHSTAN", "screenedIin": "220840001616",
                 "sanctions": {"hits": []}, "pep": {"individuals": []}},
        "lsegExtended": {},
        "enrichment": {
            "companyInfo": {"fullName": 'ТОО "BK ТЕХ КАЗАХСТАН"', "registrationDate": "2022-08-01",
                            "director": "НУРУШЕВ АРМАН", "director_iin": "770502300236",
                            "legalForm": "ТОО", "industry": "ПО", "employees": 20,
                            "address": "Алматы", "operatingStatus": "действующая"},
            "requisites": {"bank": "Freedom Bank", "iik": "KZ09", "bik": "KSNVKZKA"},
            "taxes": {"debt": 0, "status": "clean", "totalPaid": 1356330745.16, "lastPayment": "2026",
                      "yearlyPayments": [{"year": 2025, "amount": 631251959.95}]},
            "courts": {"activeCases": 3, "completedCases": 2, "totalAmount": 0, "scope": "director",
                       "note": "У компании дел нет.", "cases": []},
            "affiliates": {"companies": [{"name": "VARDITEC", "iinBin": "171040031263"}],
                           "individuals": []},
        },
        "individualCourts": {"770502300236": [
            {"number": "7528-16", "type": "Административное дело", "date": "2016-09-15",
             "court": "СМАС Алматы", "result": "Дело закрыто", "category": "ст.610"},
        ]},
    }


def test_money_formatting() -> None:
    assert _money(1356330745.16) == "1 356 330 745 ₸"
    assert _money(0) == "0 ₸"
    assert _money(None) == "—"


def test_dossier_sections_built() -> None:
    d = asyncio.run(build_dossier(_enriched()))
    assert d["company"]["fullName"] == 'ТОО "BK ТЕХ КАЗАХСТАН"'
    assert d["company"]["bin"] == "220840001616"
    assert d["taxes"]["status"] == "нет задолженности"
    assert d["taxes"]["totalPaid"] == "1 356 330 745 ₸"
    # courts: director's detailed cases surfaced
    assert d["courts"]["scope"] == "руководителя"
    assert len(d["courts"]["items"]) == 1
    assert d["courts"]["items"][0]["date"] == "2016-09-15"
    assert d["affiliates"]["companiesCount"] == 1
    assert "sanctions" in d


def test_dossier_pdf_valid() -> None:
    d = asyncio.run(build_dossier(_enriched()))
    pdf = render_dossier_pdf(d)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 3000
