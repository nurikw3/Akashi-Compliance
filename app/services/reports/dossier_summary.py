"""Deterministic, facts-only full-dossier builder (Adata + LSEG) for the PDF.

Same philosophy as the sanctions summary: compact, plain-Russian, every code
decoded, facts only — no recommendations or risk scoring. Sections:
Реквизиты · Налоги · Санкции · Судебные дела · Аффилиаты.
"""
from __future__ import annotations

from typing import Any

from app.services.reports.sanctions_summary import build_readable_summary

_TAX_STATUS_RU = {"clean": "нет задолженности", "ok": "нет задолженности", "debt": "есть задолженность"}

_COURT_CATEGORY_RU = {
    "administrative": "административное",
    "civil": "гражданское",
    "criminal": "уголовное",
    "economic": "экономическое",
    "bankruptcy": "банкротство",
    "tax": "налоговое",
    "labour": "трудовое",
    "labor": "трудовое",
    "unknown": "не определена",
}


def _money(value: Any) -> str:
    """1356330745.16 → '1 356 330 746 ₸' (без копеек, пробел-разделитель)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{int(round(n)):,}".replace(",", " ") + " ₸"


def _str(d: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return str(v)
    return default


_LEGAL_MARKERS = ("ТОО", "АО", "ООО", "ПАО", "ОАО", "ЗАО", "ПК", "ТД",
                  "LLP", "LLC", "PAO", "OOO", "GMBH", "LTD", "INC", "CORP", "PLC")


def _is_legal_entity(name: str, role: str = "") -> bool:
    """True, если «физлицо»-учредитель на деле юрлицо (АО/ТОО/…) или роль помечена «юрлицо»."""
    if "юрлиц" in (role or "").lower() or "юридическ" in (role or "").lower():
        return True
    up = " " + (name or "").upper().replace('"', " ").replace("«", " ").replace("»", " ") + " "
    return any(f" {m} " in up for m in _LEGAL_MARKERS)


def _build_company(enriched: dict) -> dict:
    en = enriched.get("enrichment") or {}
    info = en.get("companyInfo") or {}
    req = en.get("requisites") or {}
    lseg = enriched.get("lseg") or {}
    return {
        "fullName": _str(info, "fullName") or _str(req, "short_name") or enriched.get("companyName", "—"),
        "bin": _str(lseg, "screenedIin") or str(enriched.get("iin") or ""),
        "registrationDate": _str(info, "registrationDate"),
        "legalForm": _str(info, "legalForm"),
        "ownership": _str(info, "ownership"),
        "industry": _str(info, "industry"),
        "employees": _str(info, "employees"),
        "operatingStatus": _str(info, "operatingStatus"),
        "address": _str(info, "address") or _str(req, "legal_address"),
        "director": _str(info, "director"),
        "bank": _str(req, "bank"),
        "iik": _str(req, "iik"),
        "bik": _str(req, "bik"),
        "sourceLink": _str(info, "sourceLink") or _adata_company_url(
            _str(lseg, "screenedIin") or str(enriched.get("iin") or "")
        ),
        "directorUrl": _adata_individual_url(_str(info, "director_iin")),
    }


def _taxes_from(taxes: Any) -> dict | None:
    if not isinstance(taxes, dict) or not taxes:
        return None
    yp = []
    for row in (taxes.get("yearlyPayments") or [])[:6]:
        if isinstance(row, dict):
            yp.append({"year": str(row.get("year", "")), "amount": _money(row.get("amount"))})
    return {
        "status": _TAX_STATUS_RU.get(str(taxes.get("status") or "").lower(), str(taxes.get("status") or "—")),
        "debt": _money(taxes.get("debt")) if taxes.get("debt") else "нет",
        "totalPaid": _money(taxes.get("totalPaid")),
        "lastPayment": str(taxes.get("lastPayment") or ""),
        "yearlyPayments": yp,
    }


def _build_taxes(enriched: dict) -> dict | None:
    return _taxes_from((enriched.get("enrichment") or {}).get("taxes"))


def _adata_company_url(bin_iin: str) -> str:
    b = str(bin_iin or "").strip()
    return f"https://pk.adata.kz/company/{b}" if b else ""


def _adata_individual_url(iin: str) -> str:
    i = str(iin or "").strip()
    return f"https://pk.adata.kz/individual/{i}" if i else ""


def _first_doc_link(case: dict) -> str:
    for d in case.get("documents") or []:
        if isinstance(d, dict) and d.get("doc_link"):
            return str(d["doc_link"])
    return ""


def _court_item(case: dict, person_name: str = "") -> dict:
    return {
        "title": _str(case, "type", default="дело"),
        "date": _str(case, "date"),
        "court": _str(case, "court"),
        "number": _str(case, "number"),
        "docLink": _first_doc_link(case),
        "amount": _money(case.get("amount")) if case.get("amount") else "",
        # человекочитаемые поля заполняются ИИ в build_dossier (с детерм. фолбэком):
        "about": "",
        "role": "",
        "outcome": "",
        # сырое — для ИИ-разбора:
        "_raw": {
            "personName": person_name,
            "type": _str(case, "type"),
            "category": _str(case, "category"),
            "role": _str(case, "role"),
            "status": _str(case, "status"),
            "result": _str(case, "result"),
            "defendants": case.get("defendants") or [],
            "plaintiffs": case.get("plaintiffs") or [],
            "participants": case.get("participants") or [],
        },
    }


def _build_courts(enriched: dict) -> dict | None:
    en = enriched.get("enrichment") or {}
    courts = en.get("courts") or {}
    info = en.get("companyInfo") or {}
    director_iin = str(info.get("director_iin") or "")
    individual_courts = enriched.get("individualCourts") or {}

    director_name = str(info.get("director") or "")
    items: list[dict] = []
    # Детальные дела директора (если есть), иначе сводные дела из courts.cases
    director_cases = individual_courts.get(director_iin) if isinstance(individual_courts, dict) else None
    if isinstance(director_cases, list) and director_cases:
        items = [_court_item(c, director_name) for c in director_cases[:8] if isinstance(c, dict)]
    else:
        items = [_court_item(c) for c in (courts.get("cases") or [])[:8] if isinstance(c, dict)]

    # прочие физлица с делами
    other_with_cases = []
    if isinstance(individual_courts, dict):
        for iin, lst in individual_courts.items():
            if iin != director_iin and isinstance(lst, list) and lst:
                other_with_cases.append({"iin": iin, "count": len(lst)})

    if not (courts or items):
        return None
    return {
        "scope": "руководителя" if str(courts.get("scope")) == "director" else "компании",
        "note": _str(courts, "note"),
        "activeCases": courts.get("activeCases"),
        "completedCases": courts.get("completedCases"),
        "totalAmount": _money(courts.get("totalAmount")) if courts.get("totalAmount") else "0 ₸",
        "items": items,
        "otherIndividuals": other_with_cases,
    }


def _build_affiliates(enriched: dict) -> dict:
    en = enriched.get("enrichment") or {}
    aff = en.get("affiliates") or {}
    lseg_ext = enriched.get("lsegExtended") or {}
    aprofiles = enriched.get("affiliateProfiles") or {}
    individual_courts = enriched.get("individualCourts") or {}
    ic_meta = enriched.get("individualCourtsMeta") or {}
    companies = aff.get("companies") or []
    individuals = aff.get("individuals") or []

    screened_by_name: dict[str, dict] = {}
    for key, ent in lseg_ext.items():
        if isinstance(ent, dict):
            screened_by_name[str(ent.get("name") or key).strip().lower()] = ent

    def _sanction_status(name: str) -> str:
        ent = screened_by_name.get(name.strip().lower())
        if ent is None:
            return "не проверялась в санкционных списках (резидент РК)"
        if ent.get("isOnSanctionList"):
            return "НАЙДЕНО совпадение в санкционных списках"
        return "проверена — совпадений нет"

    def _director_courts(director_iin: str, director_name: str) -> list[dict]:
        cases = individual_courts.get(director_iin) if isinstance(individual_courts, dict) else None
        if not (isinstance(cases, list) and cases):
            return []
        return [_court_item(c, director_name) for c in cases[:6] if isinstance(c, dict)]

    sanctioned = []
    for key, ent in lseg_ext.items():
        if isinstance(ent, dict) and ent.get("isOnSanctionList"):
            sanctioned.append({"name": str(ent.get("name") or key), "role": str(ent.get("role") or "")})

    # ── подробные блоки по каждой компании-аффилиату (как по основной компании)
    detailed: list[dict] = []
    for c in companies[:14]:
        if not isinstance(c, dict):
            continue
        bin_val = _str(c, "iinBin", "bin")
        nm = _str(c, "name", "shortName", default="?")
        prof = aprofiles.get(bin_val) or {}
        courts = prof.get("courts") or {}
        director = _str(prof, "director")
        director_iin = _str(prof, "director_iin")
        enriched_flag = bool(prof)
        detailed.append({
            "name": nm,
            "bin": bin_val,
            "kind": "компания",
            "enriched": enriched_flag,
            "operatingStatus": _str(prof, "operatingStatus"),
            "sanctionStatus": _sanction_status(nm),
            "sourceUrl": _adata_company_url(bin_val),
            "directorUrl": _adata_individual_url(director_iin),
            "taxes": _taxes_from(prof.get("taxes")),
            "companyCourts": {
                "active": courts.get("activeCases"),
                "completed": courts.get("completedCases"),
                "totalAmount": _money(courts.get("totalAmount")) if courts.get("totalAmount") else "0 ₸",
                "hasCases": bool(courts.get("cases")),
            } if enriched_flag else None,
            "director": director,
            "directorIin": director_iin,
            "directorCourtItems": _director_courts(director_iin, director),
        })

    # ── физлица-аффилиаты (учредители-люди); юрлица-учредители помечаем как организацию
    for i in individuals[:14]:
        if not isinstance(i, dict):
            continue
        nm = _str(i, "name", default="?")
        iin = _str(i, "iin")
        is_org = _is_legal_entity(nm, _str(i, "role"))
        detailed.append({
            "name": nm,
            "bin": iin,
            "kind": "организация (учредитель)" if is_org else "физлицо",
            "enriched": bool(iin and iin in individual_courts),
            "operatingStatus": "",
            "sanctionStatus": _sanction_status(nm),
            "sourceUrl": _adata_company_url(iin) if (is_org and iin) else _adata_individual_url(iin),
            "directorUrl": "",
            "taxes": None,
            "companyCourts": None,
            "director": "",
            "directorIin": iin,
            "directorCourtItems": _director_courts(iin, nm) if iin else [],
        })

    return {
        "intro": ("Аффилированные лица — это компании и люди, связанные с контрагентом "
                  "(учредители, дочерние фирмы, общие руководители)."),
        "companiesCount": len(companies),
        "individualsCount": len(individuals),
        "screenedCount": len(lseg_ext),
        "sanctioned": sanctioned,
        "detailed": detailed,
    }


async def build_dossier(enriched: dict[str, Any]) -> dict[str, Any]:
    """Build the full facts-only dossier structure (async — sanctions + courts use LLM)."""
    sanctions = await build_readable_summary(enriched)
    courts = _build_courts(enriched)
    affiliates = _build_affiliates(enriched)

    # Собираем ВСЕ судебные дела (основной директор + директора аффилиатов) в один
    # батч ИИ-разбора, затем раскладываем «о чём / роль / итог» обратно.
    all_items: list[dict] = []
    if courts and courts.get("items"):
        all_items.extend(courts["items"])
    for aff in affiliates.get("detailed") or []:
        all_items.extend(aff.get("directorCourtItems") or [])

    if all_items:
        from app.services.reports.court_narrative import explain_courts
        narratives = await explain_courts([it.get("_raw", {}) for it in all_items])
        for i, it in enumerate(all_items):
            n = narratives.get(i) or {}
            it["about"] = n.get("about", "")
            it["role"] = n.get("role", "")
            it["outcome"] = n.get("outcome", "")
            it.pop("_raw", None)

    return {
        "company": _build_company(enriched),
        "taxes": _build_taxes(enriched),
        "sanctions": sanctions,
        "courts": courts,
        "affiliates": affiliates,
    }
