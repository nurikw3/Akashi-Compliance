from __future__ import annotations

import math
from typing import Any

from app.services.enrichment.base import BaseProvider, CompanyData
from app.services.enrichment.sources import infer_section_sources_from_data


def seeded_random(seed: str) -> float:
    hash_val = 0
    for char in seed:
        hash_val = ((hash_val << 5) - hash_val) + ord(char)
        hash_val &= 0xFFFFFFFF
    if hash_val >= 0x80000000:
        hash_val -= 0x100000000
    return abs((math.sin(hash_val) * 10000) % 1)


def stub_enrichment_dict(
    company_name: str,
    iin: str,
    data: CompanyData | None = None,
) -> dict[str, Any]:
    random = seeded_random(iin)
    has_debt = random > 0.6
    has_courts = random > 0.5
    has_sanctions = random > 0.9

    debt = int(data.tax_debt) if data and data.tax_debt is not None else 0
    if debt == 0 and has_debt:
        debt = math.floor(seeded_random(iin + "debt") * 5_000_000) + 100_000

    active_cases = int(data.court_cases) if data and data.court_cases is not None else 0
    if active_cases == 0 and has_courts:
        active_cases = math.floor(seeded_random(iin + "court") * 3) + 1

    in_sanctions = bool(data.in_sanctions_list) if data and data.in_sanctions_list is not None else has_sanctions

    industries = ["IT", "Строительство", "Торговля", "Производство", "Услуги"]
    industry_idx = math.floor(seeded_random(iin + "ind") * len(industries))

    court_cases_list: list[dict[str, Any]] = []
    if active_cases > 0:
        court_cases_list = [
            {"type": "Гражданское", "amount": 2_500_000, "date": "2024-02-10", "status": "В процессе"},
            {"type": "Административное", "amount": 150_000, "date": "2023-11-05", "status": "Завершено"},
        ]

    return {
        "companyInfo": {
            "fullName": data.name if data and data.name else f'ТОО "{company_name}"',
            "registrationDate": (data.registration_date if data else None) or "2018-03-15",
            "address": (data.address if data else None) or "г. Алматы, ул. Абая, д. 52, офис 301",
            "director": (data.director if data else None) or "Иванов Сергей Петрович",
            "employees": (data.employees if data and data.employees is not None else math.floor(seeded_random(iin + "emp") * 200) + 10),
            "industry": (data.industry if data else None) or industries[industry_idx],
        },
        "taxes": {
            "debt": debt,
            "lastPayment": "2024-01-15",
            "status": "clean" if debt <= 0 else ("critical" if random > 0.8 else "debt"),
        },
        "courts": {
            "activeCases": active_cases,
            "completedCases": math.floor(seeded_random(iin + "comp") * 5),
            "totalAmount": math.floor(seeded_random(iin + "amount") * 10_000_000) if active_cases else 0,
            "cases": court_cases_list,
        },
        "sanctions": {
            "isOnList": in_sanctions,
            "lists": ["OFAC SDN List"] if in_sanctions else [],
        },
        "affiliates": {
            "companies": [
                {"name": 'ТОО "Альфа Групп"', "iinBin": "123456789012", "role": "Учредитель"},
                {"name": 'ТОО "Бета Сервис"', "iinBin": "987654321098", "role": "Директор"},
            ],
            "individuals": [
                {"name": "Иванов С.П.", "iin": "850101350123", "role": "Директор"},
                {"name": "Петров А.Н.", "iin": "900515400456", "role": "Учредитель (30%)"},
            ],
        },
    }


class StubProvider(BaseProvider):
    name = "stub"

    def is_available(self) -> bool:
        return True

    async def check(self, iin: str) -> CompanyData:
        random = seeded_random(iin)
        has_debt = random > 0.6
        has_courts = random > 0.5
        has_sanctions = random > 0.9

        debt = 0.0
        if has_debt:
            debt = math.floor(seeded_random(iin + "debt") * 5_000_000) + 100_000

        court_cases = 0
        if has_courts:
            court_cases = math.floor(seeded_random(iin + "court") * 3) + 1

        company = CompanyData(
            iin=iin,
            status="active",
            tax_debt=debt,
            court_cases=court_cases,
            in_sanctions_list=has_sanctions,
            director="Иванов Сергей Петрович",
            founders=[
                {"name": "Петров А.Н.", "iin": "900515400456", "role": "Учредитель (30%)"},
            ],
            related_companies=[
                {"name": 'ТОО "Альфа Групп"', "iinBin": "123456789012", "role": "Учредитель"},
                {"name": 'ТОО "Бета Сервис"', "iinBin": "987654321098", "role": "Директор"},
            ],
            raw={"source": "stub"},
        )
        company.section_sources = infer_section_sources_from_data(company, "stub")
        return company
