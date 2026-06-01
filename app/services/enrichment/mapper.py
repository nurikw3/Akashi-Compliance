from __future__ import annotations

from typing import Any

from app.services.enrichment.base import CompanyData
from app.services.risk.service import RiskService


def empty_enrichment(company_name: str, iin: str) -> dict[str, Any]:
    """Neutral empty shell — no seeded fake court/affiliate rows."""
    return {
        "companyInfo": {
            "fullName": company_name or f"ИИН {iin}",
            "registrationDate": "—",
            "address": "—",
            "director": "—",
            "employees": 0,
            "industry": "—",
            "legalForm": None,
            "ownership": None,
            "sourceLink": None,
            "operatingStatus": None,
        },
        "statusFlags": [],
        "riskFlags": [],
        "taxes": {
            "debt": 0,
            "lastPayment": "—",
            "status": "clean",
            "totalPaid": None,
            "yearlyPayments": [],
        },
        "contacts": {"phones": [], "emails": [], "websites": []},
        "requisites": {},
        "courts": {
            "activeCases": 0,
            "completedCases": 0,
            "totalAmount": 0,
            "cases": [],
            "scope": "company",
            "note": None,
        },
        "sanctions": {
            "isOnList": False,
            "lists": [],
            "statusFlags": [],
            "riskFlags": [],
        },
        "affiliates": {
            "companies": [],
            "individuals": [],
        },
    }


def build_assessment(enrichment: dict[str, Any]) -> dict[str, Any]:
    flags: list[dict[str, str]] = []
    risk_score = 0

    taxes = enrichment.get("taxes", {})
    debt = taxes.get("debt", 0)
    tax_status = taxes.get("status", "clean")
    if debt > 0:
        risk_score += 3 if tax_status == "critical" else 1
        flags.append(
            {
                "type": "danger" if tax_status == "critical" else "warning",
                "message": f"Налоговая задолженность: {debt:,} тг".replace(",", " "),
            }
        )

    courts = enrichment.get("courts", {})
    active = courts.get("activeCases", 0)
    if active > 0:
        risk_score += 2
        note = courts.get("note") or ""
        flags.append(
            {
                "type": "warning",
                "message": f"Судебные дела ({courts.get('scope', 'company')}): {active}. {note}".strip(),
            }
        )

    for msg in enrichment.get("statusFlags", [])[:5]:
        risk_score += 2
        flags.append({"type": "warning", "message": msg})

    for msg in enrichment.get("riskFlags", [])[:8]:
        risk_score += 3 if any(w in msg.lower() for w in ("террор", "банкрот", "чси", "арест")) else 1
        flags.append(
            {
                "type": "danger"
                if any(w in msg.lower() for w in ("террор", "банкрот", "педофил", "розыск"))
                else "warning",
                "message": msg,
            }
        )

    sanctions = enrichment.get("sanctions", {})
    if sanctions.get("isOnList"):
        risk_score += 5
        lists = sanctions.get("lists", [])
        if lists:
            flags.append(
                {
                    "type": "danger",
                    "message": f"Факторы комплаенса: {', '.join(lists)}",
                }
            )

    if risk_score >= 4:
        risk_level = "high"
    elif risk_score >= 2:
        risk_level = "medium"
    else:
        risk_level = "low"

    summaries = {
        "low": "Компания не имеет существенных рисков. Финансовое состояние стабильное, судебных споров нет, в санкционных списках не числится.",
        "medium": "Выявлены факторы, требующие внимания. Рекомендуется дополнительная проверка перед заключением крупных сделок.",
        "high": "Высокий уровень риска. Обнаружены критические факторы, требующие детального анализа и согласования с руководством.",
    }
    recommendations = {
        "low": ["Стандартная процедура согласования", "Мониторинг раз в квартал"],
        "medium": [
            "Запросить дополнительные документы",
            "Проверить аффилированных лиц",
            "Установить лимит на сумму контракта",
        ],
        "high": [
            "Согласование с комплаенс-комитетом обязательно",
            "Провести расширенную due diligence",
            "Рассмотреть отказ от сотрудничества",
        ],
    }

    return {
        "riskLevel": risk_level,
        "summary": summaries[risk_level],
        "recommendations": recommendations[risk_level],
        "flags": flags,
    }


def _apply_courts_from_data(enrichment: dict[str, Any], data: CompanyData) -> None:
    courts = enrichment["courts"]
    ui_cases = data.raw.get("_court_ui_cases") if data.raw else None
    totals = data.court_totals or (data.raw.get("_court_totals") if data.raw else None) or {}

    courts["cases"] = []
    courts["activeCases"] = 0
    courts["completedCases"] = 0
    courts["totalAmount"] = 0

    if data.raw:
        courts["scope"] = data.raw.get("courts_scope", "company")
        courts["note"] = data.raw.get("courts_note")

    if data.court_cases is not None:
        courts["activeCases"] = int(data.court_cases)

    if totals:
        total_all = sum(int(v) for v in totals.values())
        courts["completedCases"] = max(0, total_all - courts.get("activeCases", 0))

    if ui_cases:
        courts["cases"] = list(ui_cases)
    elif data.court_cases_years:
        courts["cases"] = [
            {
                "type": f"Сводка за {row.get('year', '')}",
                "amount": 0,
                "date": str(row.get("year", "")),
                "status": (
                    f"Г:{row.get('civil_count', 0)} "
                    f"У:{row.get('criminal_count', 0)} "
                    f"А:{row.get('administrative_count', 0)} "
                    f"АППК:{row.get('appk_count', 0)}"
                ),
            }
            for row in data.court_cases_years
            if sum(
                int(row.get(k) or 0)
                for k in (
                    "civil_count",
                    "criminal_count",
                    "administrative_count",
                    "appk_count",
                )
            )
            > 0
        ]


def _is_adata_section(sources: dict[str, str], section: str) -> bool:
    return sources.get(section) == "adata"


_SANCTION_FLAG_KEYWORDS = (
    "террор",
    "экстрем",
    "санкц",
    "розыск",
    "запрещ",
    "лжепредпр",
    "педофил",
    "банкрот",
)


def _sanction_related_flag_labels(
    status_flags: list[str], risk_flags: list[str]
) -> list[str]:
    combined = list(status_flags) + list(risk_flags)
    return [
        flag
        for flag in combined
        if any(word in flag.lower() for word in _SANCTION_FLAG_KEYWORDS)
    ]


def company_data_to_enrichment(
    company_name: str, data: CompanyData
) -> dict[str, Any]:
    sources = data.section_sources or {}
    display_name = data.name or company_name or ""
    enrichment = empty_enrichment(display_name, data.iin)

    extra = (data.raw or {}).get("_company_extra") or {}

    if _is_adata_section(sources, "companyInfo") or data.name or data.director:
        if data.name:
            enrichment["companyInfo"]["fullName"] = data.name
        if data.director:
            enrichment["companyInfo"]["director"] = data.director
        if data.address:
            enrichment["companyInfo"]["address"] = data.address
        if data.registration_date:
            enrichment["companyInfo"]["registrationDate"] = data.registration_date
        if data.employees is not None:
            enrichment["companyInfo"]["employees"] = data.employees
        if data.industry:
            enrichment["companyInfo"]["industry"] = data.industry
        if data.status:
            enrichment["companyInfo"]["operatingStatus"] = data.status
        if extra.get("legalForm"):
            enrichment["companyInfo"]["legalForm"] = extra["legalForm"]
        if extra.get("ownership"):
            enrichment["companyInfo"]["ownership"] = extra["ownership"]
        if extra.get("sourceLink"):
            enrichment["companyInfo"]["sourceLink"] = extra["sourceLink"]

    enrichment["statusFlags"] = list(data.status_flags or [])
    enrichment["riskFlags"] = list(data.risk_flags or [])

    if _is_adata_section(sources, "taxes"):
        if data.tax_debt is not None:
            enrichment["taxes"]["debt"] = int(data.tax_debt)
            enrichment["taxes"]["status"] = (data.raw or {}).get(
                "tax_status",
                "critical"
                if data.tax_debt >= 1_000_000
                else ("debt" if data.tax_debt > 0 else "clean"),
            )
        if data.tax_payments_total is not None:
            enrichment["taxes"]["totalPaid"] = data.tax_payments_total
        if data.tax_payments_yearly:
            enrichment["taxes"]["yearlyPayments"] = data.tax_payments_yearly
        if extra.get("lastPayment"):
            enrichment["taxes"]["lastPayment"] = str(extra["lastPayment"])

    if data.contacts:
        enrichment["contacts"] = {
            "phones": list(data.contacts.get("phones") or []),
            "emails": list(data.contacts.get("emails") or []),
            "websites": list(data.contacts.get("websites") or []),
        }
    if data.requisites:
        enrichment["requisites"] = dict(data.requisites)

    if _is_adata_section(sources, "courts"):
        _apply_courts_from_data(enrichment, data)
    elif data.court_cases is not None or data.court_cases_years:
        _apply_courts_from_data(enrichment, data)

    if _is_adata_section(sources, "sanctions"):
        enrichment["sanctions"]["isOnList"] = bool(data.in_sanctions_list)
        enrichment["sanctions"]["lists"] = list(enrichment["sanctions"]["lists"])
        if data.in_sanctions_list:
            enrichment["sanctions"]["lists"] = _sanction_related_flag_labels(
                enrichment["statusFlags"], enrichment["riskFlags"]
            )
        enrichment["sanctions"]["statusFlags"] = enrichment["statusFlags"]
        enrichment["sanctions"]["riskFlags"] = enrichment["riskFlags"]

    if _is_adata_section(sources, "affiliates"):
        enrichment["affiliates"]["companies"] = [
            {
                "name": c.get("name", ""),
                "iinBin": c.get("iinBin") or c.get("bin", ""),
                "role": c.get("role", ""),
            }
            for c in (data.related_companies or [])
        ]
        enrichment["affiliates"]["individuals"] = [
            {
                "name": f.get("name", ""),
                "iin": f.get("iin", ""),
                "role": f.get("role", ""),
            }
            for f in (data.founders or [])
        ]

    return enrichment


def risk_from_company_data(data: CompanyData):
    return RiskService().calculate(data)


def build_graph(enrichment: dict[str, Any], main_name: str, main_iin: str) -> dict[str, Any]:
    nodes = [{"id": main_iin, "label": main_name, "type": "company", "main": True}]
    links: list[dict[str, str]] = []

    for company in enrichment.get("affiliates", {}).get("companies", []):
        cid = company.get("iinBin") or company.get("name", "")
        if not cid or cid == main_iin:
            continue
        nodes.append({"id": cid, "label": company.get("name", ""), "type": "company"})
        links.append({"source": main_iin, "target": cid, "label": company.get("role", "")})

    for person in enrichment.get("affiliates", {}).get("individuals", []):
        pid = person.get("iin") or person.get("name", "")
        if not pid:
            continue
        nodes.append({"id": pid, "label": person.get("name", ""), "type": "person"})
        links.append({"source": pid, "target": main_iin, "label": person.get("role", "")})

    return {"nodes": nodes, "links": links}
