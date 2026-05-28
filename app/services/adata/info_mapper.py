"""Map Adata ``company/info`` ``data`` object to CompanyData and section sources.

Field names follow the official Adata info API schema (basic, status, riskFactor, …).
"""

from __future__ import annotations

from typing import Any

# status + basic express indicators
_STATUS_BOOL_FLAGS: tuple[tuple[str, str], ...] = (
    ("pseudo_company", "В реестре лжепредприятий"),
    ("bankcrupt", "Банкрот"),
    ("inactive", "Неактивный налогоплательщик"),
    ("absent_at_address", "Отсутствует по юридическому адресу"),
    ("registration_invalid", "Регистрация признана недействительной"),
    ("violation_tax", "Реорганизация с нарушениями Налогового кодекса"),
    ("financial_problems", "Финансовые проблемы"),
)

_BASIC_BOOL_FLAGS: tuple[tuple[str, str], ...] = (
    ("company_problems", "Критические проблемы предприятия"),
    ("financial_problems", "Финансовые проблемы (КГД)"),
    ("unreliable_zakup", "Недобросовестный поставщик (госзакуп)"),
    ("head_problems", "Проблемы у руководителя"),
)

_RISK_COMPANY_FLAGS: tuple[tuple[str, str], ...] = (
    ("irresponsible_taxpayer", "Недобросовестный налогоплательщик (КГД)"),
    ("liquidating_taxpayer", "В процессе ликвидации"),
    ("ban_leaving", "Запрет на выезд"),
    ("enforcement_debt", "Исполнительное производство (ЧСИ)"),
    ("seized_property", "Арест имущества"),
    ("seized_bank_account", "Арест банковского счёта"),
    ("ban_registration_actions_legal_ent", "Запрет регистрационных действий"),
    ("bankruptcy_decision", "Решение о банкротстве"),
    ("bankruptcy_liquidation", "Процедура ликвидации банкрота"),
    ("bankruptcy_rehabilitation", "Процедура реабилитации"),
    ("bankrupt", "Банкротство"),
)

_RISK_HEAD_FLAGS: tuple[tuple[str, str], ...] = (
    ("terrorist", "Связь с финансированием терроризма"),
    ("terrorism_involved", "Причастность к экстремизму"),
    ("pedophile", "Реестр педофилов"),
    ("alimony_payer", "Неплательщик алиментов"),
    ("missing", "Пропал без вести"),
    ("citizen_hiding_from_investigation", "Скрывается от следствия"),
)


def _status_label(status_block: dict[str, Any], basic: dict[str, Any]) -> str:
    if status_block.get("inactive") or status_block.get("bankcrupt"):
        return "приостановлена"
    if status_block.get("registration_invalid"):
        return "регистрация недействительна"
    company_status = status_block.get("company_status")
    if company_status is True:
        return "действующая"
    if company_status is False:
        return "не действует"
    if basic.get("end_date"):
        return "ликвидирована"
    return "неизвестно"


def _collect_bool_flags(block: dict[str, Any], mapping: tuple[tuple[str, str], ...]) -> list[str]:
    flags: list[str] = []
    for key, label in mapping:
        if block.get(key) is True:
            flags.append(label)
    return flags


def _collect_status_flags(status_block: dict[str, Any], basic: dict[str, Any]) -> list[str]:
    flags = _collect_bool_flags(status_block, _STATUS_BOOL_FLAGS)
    flags.extend(_collect_bool_flags(basic, _BASIC_BOOL_FLAGS))
    if status_block.get("company_status") is False:
        flags.append("Предприятие не действует")
    return list(dict.fromkeys(flags))


def _collect_risk_flags(risk: dict[str, Any] | None) -> list[str]:
    if not isinstance(risk, dict):
        return []

    flags: list[str] = []
    company = risk.get("company") if isinstance(risk.get("company"), dict) else {}
    head = risk.get("head") if isinstance(risk.get("head"), dict) else {}

    flags.extend(_collect_bool_flags(company, _RISK_COMPANY_FLAGS))

    degree = company.get("tax_risk_degree")
    if isinstance(degree, str) and degree.strip():
        flags.append(f"Налоговый риск: {degree.strip()}")

    for key, label in (("ban_leaving_sum", "Сумма долга (запрет выезда)"),):
        val = company.get(key.replace("_sum", "")) or company.get(key)
        if isinstance(val, (int, float)) and val > 0:
            flags.append(f"{label}: {val:,.0f} тг".replace(",", " "))

    if isinstance(company.get("enforcement_debt_sum"), (int, float)) and company["enforcement_debt_sum"] > 0:
        flags.append(f"Долг ЧСИ (компания): {company['enforcement_debt_sum']:,.0f} тг".replace(",", " "))

    flags.extend(_collect_bool_flags(head, _RISK_HEAD_FLAGS))

    if isinstance(head.get("tax_debt"), (int, float)) and head["tax_debt"] > 0:
        flags.append(f"Налоговый долг руководителя: {head['tax_debt']:,.0f} тг".replace(",", " "))
    if isinstance(head.get("enforcement_debt_sum"), (int, float)) and head["enforcement_debt_sum"] > 0:
        flags.append(f"Долг ЧСИ (руководитель): {head['enforcement_debt_sum']:,.0f} тг".replace(",", " "))

    return list(dict.fromkeys(flags))


def _tax_status(debt: float, status_block: dict[str, Any]) -> str:
    if debt <= 0:
        return "clean"
    if debt >= 1_000_000 or status_block.get("violation_tax"):
        return "critical"
    return "debt"


def _litigation_totals(block: dict[str, Any]) -> int:
    if not block:
        return 0
    return (
        int(block.get("total_civil_count") or 0)
        + int(block.get("total_criminal_count") or 0)
        + int(block.get("total_administrative_count") or 0)
        + int(block.get("total_appk_count") or 0)
    )


def _litigation_block(info_data: dict[str, Any]) -> tuple[dict[str, Any], str, str | None]:
    company_lit = info_data.get("litigation")
    if not isinstance(company_lit, dict):
        company_lit = {}

    risk = info_data.get("riskFactor")
    head_lit: dict[str, Any] = {}
    if isinstance(risk, dict):
        head = risk.get("head")
        if isinstance(head, dict) and isinstance(head.get("litigation"), dict):
            head_lit = head["litigation"]

    company_total = _litigation_totals(company_lit)
    head_total = _litigation_totals(head_lit)

    if company_total > 0:
        return company_lit, "company", None
    if head_total > 0:
        basic = info_data.get("basic") if isinstance(info_data.get("basic"), dict) else {}
        director_name = basic.get("fullname_director") or ""
        note = (
            f"У компании судебных дел нет. Ниже — дела руководителя"
            f"{f' ({director_name})' if director_name else ''}."
        )
        return head_lit, "director", note
    return company_lit, "company", None


def _parse_courtcase_data(data: dict[str, Any]) -> tuple[
    int | None,
    list[dict[str, Any]],
    dict[str, int],
    list[dict[str, Any]],
]:
    if not data:
        return None, [], {}, []

    totals = {
        "civil": int(data.get("total_civil_count") or 0),
        "criminal": int(data.get("total_criminal_count") or 0),
        "administrative": int(data.get("total_administrative_count") or 0),
        "appk": int(data.get("total_appk_count") or 0),
    }
    total_count = sum(totals.values())

    years_raw = data.get("court_cases") or []
    years: list[dict[str, Any]] = []
    cases_for_ui: list[dict[str, Any]] = []

    for row in years_raw:
        if not isinstance(row, dict):
            continue
        year = str(row.get("year", ""))
        civil = int(row.get("civil_count") or 0)
        criminal = int(row.get("criminal_count") or 0)
        administrative = int(row.get("administrative_count") or 0)
        appk = int(row.get("appk_count") or 0)
        year_total = civil + criminal + administrative + appk
        years.append(
            {
                "year": year,
                "civil_count": civil,
                "criminal_count": criminal,
                "administrative_count": administrative,
                "appk_count": appk,
            }
        )
        if year_total > 0:
            cases_for_ui.append(
                {
                    "type": f"Сводка за {year}",
                    "amount": 0,
                    "date": year,
                    "status": f"Г:{civil} У:{criminal} А:{administrative} АППК:{appk}",
                }
            )

    active: int | None = total_count if total_count else None
    if years:
        recent = sorted(years, key=lambda y: y.get("year", ""), reverse=True)[:3]
        recent_sum = sum(
            y["civil_count"] + y["criminal_count"] + y["administrative_count"] + y["appk_count"]
            for y in recent
        )
        if recent_sum:
            active = recent_sum

    return active, years, totals, cases_for_ui


def _normalize_bin(item: dict[str, Any]) -> str:
    raw = (
        item.get("bin")
        or item.get("bin_formatted")
        or item.get("biin")
        or item.get("iinBin")
        or ""
    )
    return "".join(ch for ch in str(raw) if ch.isdigit())


def _parse_affiliates(
    diagram: dict[str, Any], *, main_iin: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    founders: list[dict[str, Any]] = []
    by_bin: dict[str, dict[str, Any]] = {}

    def _add_company(item: dict[str, Any], role: str) -> None:
        bin_val = _normalize_bin(item)
        if len(bin_val) != 12 or bin_val == main_iin:
            return
        role_text = str(item.get("type") or role).strip()
        if bin_val in by_bin:
            existing_roles = by_bin[bin_val].get("role", "")
            if role_text and role_text not in existing_roles:
                by_bin[bin_val]["role"] = f"{existing_roles}, {role_text}"
            return
        by_bin[bin_val] = {
            "name": item.get("name", "—"),
            "iinBin": bin_val,
            "role": role_text or role,
        }

    for item in diagram.get("affiliation_by_company") or []:
        if isinstance(item, dict):
            _add_company(item, "Связанная компания")

    by_head = diagram.get("affiliation_by_head") or {}
    if isinstance(by_head, dict):
        head_name = by_head.get("head_name", "")
        for item in by_head.get("companies") or []:
            if isinstance(item, dict):
                role = item.get("type") or "Связь"
                if head_name and "руковод" not in str(role).lower():
                    role = f"{role} ({head_name})"
                _add_company(item, role)

    for founder_block in diagram.get("affiliation_by_founder") or []:
        if not isinstance(founder_block, dict):
            continue
        founders.append(
            {
                "name": founder_block.get("founder_name", "—"),
                "iin": str(
                    founder_block.get("founder_biin_formatted")
                    or founder_block.get("founder_biin")
                    or ""
                ),
                "role": "Учредитель",
            }
        )
        for item in founder_block.get("companies") or []:
            if isinstance(item, dict):
                _add_company(item, "Компания учредителя")

    return list(by_bin.values()), founders


def _founders_from_block(founders_block: dict[str, Any]) -> list[dict[str, Any]]:
    individuals: list[dict[str, Any]] = []
    for item in founders_block.get("founders_dtl") or []:
        if not isinstance(item, dict):
            continue
        uin = str(
            item.get("founder_uin_formatted")
            or item.get("founder_uin")
            or item.get("founder_biin")
            or ""
        )
        role = "Учредитель (юрлицо)" if item.get("is_company") else "Учредитель"
        if item.get("start_date"):
            role += f" (с {item['start_date']})"
        individuals.append(
            {
                "name": item.get("name", "—"),
                "iin": uin,
                "role": role,
            }
        )
    return individuals


def _parse_tax_deductions(info_data: dict[str, Any]) -> tuple[float | None, list[dict[str, Any]], str]:
    block = info_data.get("taxDeductions")
    if not isinstance(block, dict):
        return None, [], "—"

    total_raw = block.get("sum")
    total = float(total_raw) if total_raw is not None else None
    yearly: list[dict[str, Any]] = []
    for row in block.get("details") or []:
        if not isinstance(row, dict):
            continue
        year = row.get("year")
        amount = row.get("amount")
        if year is None or amount is None:
            continue
        yearly.append({"year": int(year), "amount": float(amount)})

    yearly.sort(key=lambda r: r["year"], reverse=True)
    last_payment = str(yearly[0]["year"]) if yearly else "—"
    return total, yearly, last_payment


def _parse_contacts(info_data: dict[str, Any]) -> dict[str, list[str]]:
    block = info_data.get("kzCoContact")
    if not isinstance(block, dict):
        return {"phones": [], "emails": [], "websites": []}

    def _strings(key: str) -> list[str]:
        raw = block.get(key) or []
        if not isinstance(raw, list):
            return []
        return [str(x).strip() for x in raw if str(x).strip()]

    return {
        "phones": _strings("phones"),
        "emails": _strings("emails"),
        "websites": _strings("websites"),
    }


def _parse_requisites(info_data: dict[str, Any]) -> dict[str, Any]:
    block = info_data.get("requisites")
    if not isinstance(block, dict):
        return {}
    return {
        k: block.get(k)
        for k in ("iik", "bank", "bik", "kbe_code", "short_name", "legal_address")
        if block.get(k) not in (None, "")
    }


def _has_critical_risk(risk_flags: list[str], status_flags: list[str]) -> bool:
    critical_keywords = (
        "террор",
        "экстрем",
        "банкрот",
        "лжепредпр",
        "недействительн",
        "педофил",
        "розыск",
    )
    combined = " ".join(risk_flags + status_flags).lower()
    return any(word in combined for word in critical_keywords)


def map_info_data(
    iin: str,
    info_data: dict[str, Any],
    *,
    company_name: str = "",
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Returns dict with keys matching CompanyData fields plus
    ``section_sources``, ``_court_*`` helpers, ``tax_status``.
    """
    basic = info_data.get("basic") if isinstance(info_data.get("basic"), dict) else {}
    status_block = info_data.get("status") if isinstance(info_data.get("status"), dict) else {}
    diagram = (
        info_data.get("connectedDiagram")
        if isinstance(info_data.get("connectedDiagram"), dict)
        else {}
    )
    founders_block = info_data.get("founders") if isinstance(info_data.get("founders"), dict) else {}
    risk = info_data.get("riskFactor") if isinstance(info_data.get("riskFactor"), dict) else None

    name = (
        basic.get("short_name")
        or basic.get("name_ru")
        or basic.get("name_kgd")
        or company_name
        or None
    )
    director = basic.get("fullname_director") or basic.get("director")
    address = basic.get("legal_address") or basic.get("legal_address_kz")
    registration_date = basic.get("date_registration") or basic.get("last_date_registration")
    employees = basic.get("employee_count")
    industry = basic.get("oked")
    okeds = basic.get("okeds")
    if not industry and isinstance(okeds, list) and okeds and isinstance(okeds[0], dict):
        industry = okeds[0].get("name_ru")

    legal_form = basic.get("legal_form")
    ownership = basic.get("type_of_ownership")
    source_link = basic.get("source_link")

    tax_debt = status_block.get("tax_debt")
    if tax_debt is None:
        tax_debt = basic.get("tax_debt")
    tax_debt_f = float(tax_debt) if tax_debt is not None else None
    tax_status = _tax_status(tax_debt_f or 0, status_block)

    tax_total, tax_yearly, last_payment_year = _parse_tax_deductions(info_data)
    contacts = _parse_contacts(info_data)
    requisites = _parse_requisites(info_data)

    status_flags = _collect_status_flags(status_block, basic)
    risk_flags = _collect_risk_flags(risk)

    lit_data, courts_scope, courts_note = _litigation_block(info_data)
    court_active, court_years, court_totals, court_ui = _parse_courtcase_data(lit_data)
    has_courts = (court_active is not None and court_active > 0) or bool(court_years)

    related, founders_aff = _parse_affiliates(diagram, main_iin=iin)
    founders_list = _founders_from_block(founders_block) or founders_aff
    if founders_aff:
        names = {f["name"] for f in founders_list}
        for f in founders_aff:
            if f["name"] not in names:
                founders_list.append(f)

    in_sanctions = _has_critical_risk(risk_flags, status_flags) or bool(risk_flags)
    status_text = _status_label(status_block, basic)

    has_company = bool(name or director or address)
    has_tax = tax_debt_f is not None or tax_total is not None
    has_affiliates = bool(related or founders_list)
    has_contacts = any(contacts.values())

    section_sources = {
        "companyInfo": "adata" if has_company else "stub",
        "taxes": "adata" if has_tax else "stub",
        "courts": "adata" if has_courts or lit_data else "stub",
        "sanctions": "adata" if risk is not None else "stub",
        "affiliates": "adata" if has_affiliates else "stub",
        "graph": "adata" if has_affiliates else "stub",
        "assessment": "stub",
        "conclusion": "stub",
    }

    wrapper = raw if raw is not None else {"info": {"success": True, "data": info_data}}
    wrapper["_section_sources"] = section_sources
    wrapper["_courts_source"] = section_sources["courts"]
    wrapper["_court_ui_cases"] = court_ui
    wrapper["_court_totals"] = court_totals
    wrapper["courts_scope"] = courts_scope
    wrapper["courts_note"] = courts_note
    wrapper["tax_status"] = tax_status
    wrapper["_company_extra"] = {
        "legalForm": legal_form,
        "ownership": ownership,
        "sourceLink": source_link,
        "lastPayment": last_payment_year,
    }

    return {
        "iin": iin,
        "name": str(name) if name else None,
        "status": status_text,
        "tax_debt": tax_debt_f,
        "court_cases": court_active,
        "court_cases_years": court_years,
        "court_totals": court_totals,
        "in_sanctions_list": in_sanctions,
        "director": str(director) if director else None,
        "address": str(address) if address else None,
        "registration_date": str(registration_date) if registration_date else None,
        "employees": int(employees) if employees is not None else None,
        "industry": str(industry) if industry else None,
        "founders": founders_list,
        "related_companies": related,
        "status_flags": status_flags,
        "risk_flags": risk_flags,
        "tax_payments_total": tax_total,
        "tax_payments_yearly": tax_yearly,
        "contacts": contacts if has_contacts else contacts,
        "requisites": requisites,
        "section_sources": section_sources,
        "raw": wrapper,
    }


def info_has_structured_blocks(info_data: dict[str, Any]) -> bool:
    """True when payload matches unified info API (basic + status blocks)."""
    return isinstance(info_data.get("basic"), dict) or isinstance(info_data.get("status"), dict)
