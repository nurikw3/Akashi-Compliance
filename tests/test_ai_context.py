from __future__ import annotations

from app.services.ai.context import build_case_context

SAMPLE = {
    "companyInfo": {
        "fullName": 'ТОО "TEST"',
        "director": "Иванов И.И.",
        "registrationDate": "2020-01-01",
        "address": "Алматы",
        "employees": 10,
        "industry": "IT",
    },
    "taxes": {"debt": 1000, "status": "debt", "lastPayment": "2023"},
    "courts": {"activeCases": 2, "scope": "company", "cases": []},
    "affiliates": {
        "companies": [{"name": "Связанная", "iinBin": "123456789012", "role": "Учредитель"}],
        "individuals": [],
    },
    "riskFlags": ["Налоговый риск: средняя"],
}


def test_build_case_context_includes_sections():
    text = build_case_context(
        company_name='ТОО "TEST"',
        iin="123456789012",
        enrichment=SAMPLE,
        assessment={"flags": [{"type": "fact", "message": "Налоговая задолженность: 1 000 тг"}]},
        conclusion="Тестовое заключение",
    )
    assert "ТОО" in text
    assert "Налоговый риск" in text
    assert "Связанная" in text
    assert "Тестовое заключение" in text
