"""Full compliance AI report generator.

Собирает все данные кейса (основная компания + LSEG + trustworthy-plus +
beneficiary + non-residents + relation + affiliate tree) и генерирует
структурированный отчёт через LLM.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.models import db
from app.services.ai.context import resolve_individual_courts_key
from app.services.ai.court_roles import (
    normalize_case_role as _normalize_case_role,
    normalize_person_name_key as _normalize_person_name_key,
    party_list_role_for_person as _party_list_role_for_person,
    resolve_person_case_role as _resolve_person_case_role,
)
from app.services.affiliate_tree import normalize_bin
from app.services.verification_log import append_case_event

logger = logging.getLogger(__name__)

MISSING = "Данные отсутствуют"

_OFFICER_FOCUS = """
ЦЕЛЬ: предоставить комплаенс-офицеру ТОЛЬКО объективные факты с указанием источника.
- Конкретика: ФИО/компания, роль в деле, статья или категория, № дела, дата, статус — как в данных.
- Каждый факт начинай с источника в квадратных скобках: [Adata], [LSEG].
- ЗАПРЕЩЕНО: выводы, оценки, советы, рекомендации, уровни риска, баллы, флаги (green/yellow/red), действия.
- Если данных нет — так и напиши; не выдумывай.
"""

_COURTS_DEAL_POLICY = """
ЗАДАЧА: перечислить судебные дела как объективные факты, без оценки тяжести и влияния на сделку.

Для КАЖДОГО дела одной строкой укажи (что есть в данных):
- роль по Adata (ответчик/истец/третья сторона);
- категория/статья;
- № дела;
- дата;
- статус/результат;
- расхождение ролей (если роль в Adata не совпадает со списком сторон) — указать как факт.

ЗАПРЕЩЕНО: оценивать тяжесть, делить на red/yellow/ignore, давать выводы о влиянии на сделку,
советовать действия, ставить флаги, использовать слово «может».
ФОРМАТ: только ### Найденные факты. Если дел нет — «- Фактов по разделу не выявлено.»
"""

_SYSTEM_PROMPT_SANCTIONS_CONCLUSION = f"""Ты — комплаенс-аналитик. Раздел «Санкционный анализ».
Блок фактов LSEG/PEP УЖЕ в отчёте (код). Выведи ТОЛЬКО объективные факты:

### Найденные факты
- [LSEG] конкретный факт (санкции/PEP/списки WC1, субъект, статус).
Если фактов нет — «- Фактов по разделу не выявлено.»

ЗАПРЕЩЕНО упоминать: суды, иски, ответчик/истец, налоги, структуру, ДТП.
ЗАПРЕЩЕНО: выводы, оценки, риск-уровни, флаги, действия, рекомендации.
{_OFFICER_FOCUS}"""

SYSTEM_PROMPT_SANCTIONS = _SYSTEM_PROMPT_SANCTIONS_CONCLUSION

SYSTEM_PROMPT_COURTS = f"""Ты — комплаенс-аналитик. Раздел «Судебные дела».
Таблица дел уже в отчёте. Выведи ТОЛЬКО блок ### Найденные факты с объективными фактами по делам.
{_COURTS_DEAL_POLICY}
{_OFFICER_FOCUS}"""

_STRUCTURE_POLICY = """
ПРАВИЛА (строго):
- Пиши ТОЛЬКО о том, что есть в досье в контексте. Нет данных — напиши «данные отсутствуют».
- НЕ выдумывай UBO, владельцев, связи, которых нет в контексте.
- НЕ используй слова «предположительно», «возможно связано», «вероятно».
- Каждый факт — с источником в скобках: [Adata], [LSEG].
- ЗАПРЕЩЕНО: выводы о риске, флаги, действия, рекомендации, уровни риска.
"""

SYSTEM_PROMPT_STRUCTURE = f"""Ты — комплаенс-аналитик. Раздел «Структура и аффилиаты».
Досье по компаниям УЖЕ в отчёте (код). Выведи ТОЛЬКО блок:

### Найденные факты
- [источник] субъект + конкретный факт (санкции / суд / налог / связь), как в данных.
Если фактов нет — «- Фактов по разделу не выявлено.»
{_STRUCTURE_POLICY}
{_OFFICER_FOCUS}"""

SYSTEM_PROMPT_SUMMARY = f"""Ты — комплаенс-аналитик. Сводка фактов по контрагенту.

ПРАВИЛА (строго):
1. Используй ТОЛЬКО факты из контекста. НЕ выдумывай.
2. НЕ используй «возможно», «может указывать», «предположительно» без конкретного факта.
3. ФОРМАТ — один блок:

**Найденные факты:**
- [Adata] конкретный факт из контекста
- [LSEG] конкретный факт из контекста

4. Сгруппируй факты по источнику (Adata / LSEG). Каждый факт — отдельная строка с дефисом и источником.
5. Максимум 7 фактов. Включай только то, что реально есть в данных.
6. ЗАПРЕЩЕНО: вывод, оценка, уровень риска, балл, рекомендация, действие, флаги.
{_OFFICER_FOCUS}"""

_SECTION_PROMPTS: dict[str, str] = {
    "sanctions": SYSTEM_PROMPT_SANCTIONS,
    "courts": SYSTEM_PROMPT_COURTS,
    "structure": SYSTEM_PROMPT_STRUCTURE,
    "summary": SYSTEM_PROMPT_SUMMARY,
}


def _is_populated(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        s = value.strip()
        return bool(s) and s not in ("—", "-", "null", "None")
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _list_data_sources(enriched: dict[str, Any]) -> list[str]:
    """List exactly which enriched_data blocks are present and non-empty."""
    labels: list[tuple[str, str]] = [
        ("enrichment", "Adata (enrichment)"),
        ("lseg", "LSEG World-Check One (компания и директор)"),
        ("lsegExtended", "LSEG World-Check One (аффилиаты/нерезиденты)"),
        ("affiliateTree", "Дерево аффилиатов"),
        ("trustworthyPlus", "Adata Trustworthy-Plus"),
        ("beneficiary", "Adata Beneficiary (UBO)"),
        ("nonResidents", "Adata Non-Residents"),
        ("relationExtended", "Adata Relation Extended"),
        ("directorProfile", "Adata профиль директора (ИИН)"),
        ("affiliateProfiles", "Adata данные аффилиатов L1"),
        ("individualProfiles", "Adata профили физлиц (директор + учредители)"),
        ("individualCourts", "Adata персональные судебные дела (ИИН)"),
        ("companyCourtCases", "Adata судебные дела компании (детально)"),
    ]
    used: list[str] = []
    for key, label in labels:
        val = enriched.get(key)
        if key == "nonResidents" and isinstance(val, dict):
            if _is_populated(val.get("data")):
                used.append(label)
        elif _is_populated(val):
            used.append(label)
    return used


_RU_MATCH_STRENGTH: dict[str, str] = {
    "EXACT": "точное",
    "STRONG": "высокое",
    "MEDIUM": "среднее",
    "WEAK": "низкое",
    "PROBABLE": "вероятное",
    "POSSIBLE": "возможное",
}


def _ru_match_strength(value: Any) -> str:
    """Перевод силы совпадения LSEG на русский (иначе — как есть)."""
    raw = str(value or "").strip()
    return _RU_MATCH_STRENGTH.get(raw.upper(), raw)


def _ru_tax_status(value: Any) -> str:
    """Перевод налогового статуса (clean/debt) на русский (иначе — как есть)."""
    raw = str(value or "").strip()
    mapping = {
        "clean": "нет задолженности",
        "debt": "есть задолженность",
        "ok": "нет задолженности",
    }
    return mapping.get(raw.lower(), raw or "—")


def _lseg_hit_type(hit: dict) -> str:
    if hit.get("isSanction"):
        return "формальные санкции"
    if hit.get("isMaterialMatch"):
        return "список наблюдения (WC1)"
    return "совпадение"


def _lseg_hit_countries(hit: dict) -> str:
    names = hit.get("countryNames") or hit.get("countries") or []
    return ", ".join(str(c) for c in names[:3]) or "—"


def _lseg_hit_summary(hit: dict, *, default_name: str = "") -> str:
    """Одна читаемая строка по одному совпадению WC1 — без кодов списков."""
    name = hit.get("primaryName") or hit.get("submittedName") or default_name or "—"
    hit_type = _lseg_hit_type(hit)
    country = _lseg_hit_countries(hit)
    score = hit.get("matchScore")
    score_part = f" (score {score:.0f})" if isinstance(score, (int, float)) else ""
    return f"**{name}** — {hit_type}, {country}{score_part}"


def _format_lseg_extended_entity(entity: dict[str, Any], key: str) -> list[str]:
    """Одна строка на связанное лицо — только суть, без кодов."""
    name = entity.get("name") or key
    role = entity.get("role") or "связанное лицо"
    country = entity.get("country") or "—"
    on_list = entity.get("isOnSanctionList", False)
    hits = entity.get("hits") or []

    if not on_list and not hits:
        return []

    status = "под санкциями" if on_list else "совпадение"
    hit_names = []
    for h in hits[:2]:
        hit_names.append(_lseg_hit_summary(h, default_name=name))

    line = f"- {status} · **{name}** ({role}, {country})"
    if hit_names:
        line += " → " + "; ".join(hit_names)
    return [line]


def _format_lseg_extended_block(lseg_extended: dict[str, Any], *, max_entities: int = 15) -> str:
    """Компактный блок связанных лиц под санкциями — без кодов списков."""
    if not lseg_extended:
        return ""

    risk_lines: list[str] = []
    clean_count = 0
    for key, entity in lseg_extended.items():
        if not isinstance(entity, dict):
            continue
        on_list = entity.get("isOnSanctionList", False)
        hits = entity.get("hits") or []
        if not on_list and not hits:
            clean_count += 1
            continue
        if len(risk_lines) >= max_entities:
            continue
        risk_lines.extend(_format_lseg_extended_entity(entity, key))

    parts = []
    if risk_lines:
        parts.append("**Связанные лица под санкциями/в списке наблюдения:**")
        parts.extend(risk_lines)
    if clean_count:
        parts.append(f"- Прочие проверенные лица ({clean_count}) — чисто")
    return "\n".join(parts)


def _format_lseg_screening_summary(enriched: dict[str, Any]) -> str:
    """Читаемый блок LSEG для отчёта — без кодов списков, только суть."""
    lseg = enriched.get("lseg")
    if not _is_populated(lseg):
        return "LSEG World-Check: данные не загружены."

    lseg = lseg or {}
    lseg_extended = enriched.get("lsegExtended") or {}
    lines: list[str] = []

    # Компания
    company_hits = (lseg.get("sanctions") or {}).get("hits") or []
    if company_hits:
        lines.append("**Компания — совпадения WC1:**")
        for h in company_hits[:3]:
            lines.append(f"- {_lseg_hit_summary(h)}")
    else:
        lines.append("**Компания:** санкционных совпадений нет")

    # PEP
    pep = lseg.get("pep") or {}
    if pep.get("isHit"):
        pep_names = []
        for h in (pep.get("individuals") or [])[:2]:
            strength = _ru_match_strength(h.get("matchStrength"))
            strength_part = f" ({strength})" if strength and strength != "—" else ""
            pep_names.append(f"{h.get('primaryName', '—')}{strength_part}")
        pep_str = "; ".join(pep_names) if pep_names else "есть"
        lines.append(f"**Руководство PEP:** {pep_str}")
    else:
        lines.append("**Руководство PEP:** не выявлено")

    # Связанные лица
    if lseg_extended:
        extended_block = _format_lseg_extended_block(lseg_extended)
        if extended_block:
            lines.append(extended_block)
        else:
            lines.append("**Связанные лица:** все чисто")
    else:
        lines.append("**Связанные лица:** скрининг не выполнялся")

    return "\n".join(lines)


def _collect_affiliate_enrichments(
    affiliate_tree: dict | None, max_depth: int = 2
) -> list[dict]:
    """Walk affiliate tree, load enriched_data for nodes with hasReport=True."""

    results: list[dict] = []

    def _walk(node: dict, depth: int) -> None:
        if depth > max_depth:
            return
        iin_bin = normalize_bin(node.get("iinBin"))
        name = str(node.get("name") or "")
        has_report = node.get("hasReport", False)
        role = str(node.get("role") or "")

        if has_report and iin_bin and len(iin_bin) == 12:
            row = db.find_case_by_iin(iin_bin)
            if row:
                enriched = row.get("enriched_data") or {}
                enrichment = enriched.get("enrichment") or {}
                results.append(
                    {
                        "name": name or row.get("company_name") or MISSING,
                        "iinBin": iin_bin,
                        "role": role,
                        "level": depth,
                        "case_id": row.get("id"),
                        "courts": enrichment.get("courts"),
                        "taxes": enrichment.get("taxes"),
                        "riskFlags": enrichment.get("riskFlags") or [],
                        "sanctions": enrichment.get("sanctions"),
                        "lseg": enriched.get("lseg"),
                        "director": (enrichment.get("companyInfo") or {}).get(
                            "director"
                        ),
                    }
                )
            else:
                logger.warning(
                    "Affiliate hasReport but no case for BIN %s (%s)",
                    iin_bin,
                    name,
                )

        for child in node.get("children") or []:
            if isinstance(child, dict):
                _walk(child, depth + 1)

    if not affiliate_tree:
        return results
    root = affiliate_tree.get("root")
    if not isinstance(root, dict):
        return results
    for child in root.get("children") or []:
        if isinstance(child, dict):
            _walk(child, 1)

    return results


def _dossier_case_link(case_id: str | None, *, label: str = "открыть досье") -> str:
    if case_id:
        return f" — [{label}](/cases/{case_id})"
    return ""


_SUMMARY_COUNT_RE = re.compile(r"г:\s*\d+\s+у:\s*\d+", re.IGNORECASE)


def _should_skip_case_for_report(case: dict) -> bool:
    """Сводные/пустые записи без предмета спора — не показывать в отчёте."""
    category = str(case.get("category") or case.get("type") or "")
    result_text = str(case.get("result") or case.get("status") or "")
    # Сводные строки «Сводка за 2025 · Г:0 У:0 А:1» — счётчик может быть либо
    # в категории, либо в результате/статусе.
    if _SUMMARY_COUNT_RE.search(category) or _SUMMARY_COUNT_RE.search(result_text):
        return True
    if re.match(r"\s*сводка\b", category, re.IGNORECASE):
        return True
    ai = case.get("aiAnalysis") or {}
    summary = str(ai.get("summary_ru") or "").lower()
    if "данных недостаточно" in summary and not (case.get("defendants") or case.get("plaintiffs")):
        return True
    return False


def _is_officer_role(person_role: str) -> bool:
    lowered = person_role.lower()
    return any(m in lowered for m in ("директор", "руковод", "учред", "бенефициар"))


def _is_low_relevance_for_contract(category: str) -> bool:
    """ДТП/ПДД и мелочь — не блокируют B2B-сделку с контрагентом."""
    lowered = category.lower()
    markers = (
        "дтп",
        "дорожн",
        "610",
        "транспорт",
        "пдд",
        "нарушение водител",
        "компенсац",
        "ущерб",
        "штраф",
        "административное правонарушение",
        "административн",
    )
    if "дтп" in lowered or "дорожн" in lowered:
        return True
    if "610" in lowered and ("транспорт" in lowered or "водител" in lowered):
        return True
    if "компенсац" in lowered and ("ущерб" in lowered or "дтп" in lowered):
        return True
    return any(m in lowered for m in markers) and "семейно" not in lowered


def _contract_relevance_tier(
    case: dict,
    person_name: str,
    *,
    person_role: str = "",
) -> str:
    """red | yellow | neutral | noise — для решения о сделке с контрагентом."""
    if _should_skip_case_for_report(case):
        return "noise"

    resolved = _resolve_person_case_role(case, person_name)
    adata_role = resolved["adata_role"]
    category = str(case.get("category") or case.get("type") or "")

    serious = _is_serious_court_category(category) or _is_conviction(case)

    if _is_low_relevance_for_contract(category) and not serious:
        return "noise"

    officer = _is_officer_role(person_role)

    if adata_role == "Третья сторона":
        if resolved["has_discrepancy"]:
            return "yellow"
        # Уголовный состав / обвинительный приговор существенен даже для третьей
        # стороны — не прячем его как «шум».
        if serious:
            return "yellow"
        return "noise"

    if adata_role == "Ответчик" and _is_serious_court_category(category):
        return "red"
    if adata_role == "Ответчик" and _is_conviction(case):
        return "red"
    if adata_role == "Ответчик" and officer and (
        "налог" in category.lower() or "задолж" in category.lower()
    ):
        return "yellow"
    if adata_role == "Ответчик" and (
        "договор" in category.lower()
        or "сделк" in category.lower()
        or "спор" in category.lower()
    ):
        return "yellow"

    ai = case.get("aiAnalysis") or {}
    if adata_role == "Ответчик" and str(ai.get("severity") or "").lower() in (
        "critical",
        "high",
    ):
        return "red" if officer else "yellow"

    if adata_role == "Ответчик":
        return "neutral"
    return "neutral"


def _format_lseg_dossier_bullets(lseg: dict | None, sanctions: dict | None) -> list[str]:
    bullets: list[str] = []
    if sanctions and sanctions.get("isOnList"):
        lists = sanctions.get("lists") or []
        bullets.append(
            f"- Санкции (Adata): **есть** ({', '.join(str(x) for x in lists[:3]) or 'список не указан'})"
        )
    else:
        bullets.append("- Санкции (Adata): нет")

    if not lseg:
        bullets.append("- LSEG: не проверялось")
        return bullets

    san = lseg.get("sanctions") or {}
    pep = lseg.get("pep") or {}
    if san.get("isOnList"):
        matched = san.get("matchedLists") or []
        bullets.append(f"- LSEG санкции: **да** ({', '.join(str(m) for m in matched[:3]) or 'списки'})")
    elif pep.get("isHit"):
        bullets.append("- LSEG PEP: **совпадение**")
    else:
        bullets.append("- LSEG: чисто")
    return bullets


def _format_company_dossier_card(
    *,
    name: str,
    iin_bin: str,
    case_id: str | None = None,
    role: str = "",
    taxes: dict | None = None,
    risk_flags: list | None = None,
    lseg: dict | None = None,
    sanctions: dict | None = None,
    director: str | None = None,
) -> str:
    """Краткое досье одной компании/узла (структура: без судов, факты, без LLM).

    Судебные дела намеренно не включаются — они полностью раскрыты в разделе
    «Судебные дела». Здесь — только собственность/санкции/налоги.
    """
    link = _dossier_case_link(case_id)
    role_part = f" · {role}" if role else ""
    lines = [f"### {name}{role_part} · БИН `{iin_bin}`{link}"]
    if director:
        lines.append(f"- Директор: {_clean_person_display_name(director)}")

    lines.extend(_format_lseg_dossier_bullets(lseg, sanctions))

    if taxes:
        status = _ru_tax_status(taxes.get("status"))
        debt = taxes.get("debt", 0) or 0
        if debt and debt > 0:
            debt_str = f"{debt:,.0f}".replace(",", " ")
            lines.append(f"- Налоги: {status}, задолженность {debt_str} тг")
        else:
            lines.append(f"- Налоги: {status}")
    else:
        lines.append("- Налоги: данных нет")

    flags = risk_flags or []
    if flags:
        lines.append(f"- Риск-флаги: {'; '.join(str(f) for f in flags[:4])}")
    else:
        lines.append("- Риск-флаги: нет")

    return "\n".join(lines)


def _format_company_dossier_from_row(row: dict[str, Any]) -> str:
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    info = enrichment.get("companyInfo") or {}
    return _format_company_dossier_card(
        name=str(row.get("company_name") or MISSING),
        iin_bin=str(row.get("iin") or MISSING),
        case_id=row.get("id"),
        role="проверяемый контрагент",
        taxes=enrichment.get("taxes"),
        risk_flags=enrichment.get("riskFlags") or [],
        lseg=enriched.get("lseg"),
        sanctions=enrichment.get("sanctions"),
        director=str(info.get("director") or "") or None,
    )


def _format_company_dossier_from_affiliate(aff: dict) -> str:
    return _format_company_dossier_card(
        name=str(aff.get("name") or MISSING),
        iin_bin=str(aff.get("iinBin") or MISSING),
        case_id=aff.get("case_id"),
        role=str(aff.get("role") or ""),
        taxes=aff.get("taxes"),
        risk_flags=aff.get("riskFlags") or [],
        lseg=aff.get("lseg"),
        sanctions=aff.get("sanctions"),
        director=str(aff.get("director") or "") or None,
    )


def _build_sanctions_facts_block(row: dict[str, Any]) -> str:
    """Факты санкционного скрининга (код) — показываются в отчёте."""
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    company_name = row.get("company_name") or MISSING
    lines = ["### Результаты скрининга\n"]
    lseg_text = _format_lseg_screening_summary(
        {**enriched, "_company_name": company_name}
    )
    lines.append(lseg_text)

    adata_san = enrichment.get("sanctions") or {}
    if adata_san.get("isOnList"):
        lists = adata_san.get("lists") or []
        lines.append(
            f"\n- Adata санкции/риски: **есть** ({', '.join(str(x) for x in lists[:5])})"
        )
    else:
        lines.append("\n- Adata санкции/риски: нет")

    return "\n".join(lines)


def _sanitize_sanctions_section(text: str) -> str:
    """Убрать суды, мусорные «1.» и дубли из санкционного раздела."""
    cleaned_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if re.match(r"^[-*]\s*1\.?\s*$", stripped):
            continue
        if re.match(r"^1\.?\s*$", stripped):
            continue
        if stripped.startswith(("- ", "* ")):
            body = stripped[2:].strip()
            if _line_mentions_courts(body) and not _line_mentions_sanctions(body):
                continue
        elif _line_mentions_courts(stripped) and not _line_mentions_sanctions(stripped):
            if not stripped.startswith("#"):
                continue
        line = re.sub(
            r"(НУРУШЕВ[^.\n]*?)\s+1\.(\s|$)",
            r"\1\2",
            line,
            flags=re.IGNORECASE,
        )
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _normalize_sanctions_output(text: str) -> str:
    base = _sanitize_sanctions_section(_sanitize_llm_text(text or "").strip()) or MISSING
    return _append_facts_block("sanctions", base)


def _build_structure_dossiers_block(row: dict[str, Any]) -> str:
    enriched = row.get("enriched_data") or {}
    affiliate_tree = enriched.get("affiliateTree")
    parts = ["### Досье по компаниям\n", _format_company_dossier_from_row(row)]

    for aff in _collect_affiliate_enrichments(affiliate_tree, max_depth=2):
        parts.append(_format_company_dossier_from_affiliate(aff))

    beneficiary = enriched.get("beneficiary")
    if _is_populated(beneficiary) and isinstance(beneficiary, list):
        own_keys = _company_identity_keys(row)
        ben_lines = ["### Бенефициары (справочно)"]
        for b in beneficiary[:8]:
            name_b = b.get("name") or b.get("short_name") or MISSING
            # Сама проверяемая компания не является своим бенефициаром.
            if _normalize_person_name_key(name_b) in own_keys:
                continue
            share = b.get("share") or b.get("ownershipShare")
            share_part = f" · доля {share}" if _is_populated(share) else " · доля не указана"
            ben_lines.append(f"- {name_b}{share_part}")
        if len(ben_lines) > 1:
            parts.append("\n".join(ben_lines))

    nr_data = (enriched.get("nonResidents") or {}).get("data") if isinstance(
        enriched.get("nonResidents"), dict
    ) else []
    if _is_populated(nr_data):
        nr_lines = ["### Нерезиденты (справочно)"]
        for nr in nr_data[:8]:
            name_nr = nr.get("name") or nr.get("short_name") or MISSING
            country = nr.get("country") or nr.get("countryCode") or MISSING
            nr_lines.append(f"- {name_nr} · {country}")
        parts.append("\n".join(nr_lines))

    return "\n\n".join(parts)


def _normalize_llm_conclusion(section: str, text: str) -> str:
    base = _sanitize_llm_text(text or "").strip() or MISSING
    if "### Найденные факты" not in base:
        base = f"### Найденные факты\n{base}"
    return base


def _clean_person_display_name(name: Any) -> str:
    """Убрать артефакты вроде хвостового « 1» / « 1.» из ФИО."""
    s = re.sub(r"\s+", " ", str(name or "").strip())
    s = re.sub(r"\s+1\.?\s*$", "", s)
    return s or MISSING


def _line_mentions_courts(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "судеб",
        "суд ",
        " суд",
        "дело",
        "дела",
        "иск ",
        "исков",
        "ответчик",
        "истец",
        "дтп",
        "ст. 73",
        "ст.73",
        "статья 73",
    )
    return any(m in lowered for m in markers)


def _line_mentions_sanctions(text: str) -> bool:
    lowered = text.lower()
    return any(
        m in lowered
        for m in (
            "санкц",
            "pep",
            "lseg",
            "world-check",
            "wc1",
            "watchlist",
            "ofac",
            "список",
            "совпаден",
        )
    )


def _short_text(value: Any, *, max_len: int = 80) -> str:
    text = str(value or "—").strip()
    if not text:
        return "—"
    text = re.sub(r"\s+", " ", text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _extract_case_role_by_parties(case: dict[str, Any], person_name: str) -> str:
    """Роль для таблицы: Adata + пометка при расхождении со списком сторон."""
    return _resolve_person_case_role(case, person_name)["display_role"]


def _count_case_source_links(case: dict[str, Any]) -> int:
    count = sum(1 for d in (case.get("documents") or []) if d.get("doc_link"))
    for event in case.get("history") or []:
        count += sum(1 for d in (event.get("documents") or []) if d.get("doc_link"))
    return count


def _is_serious_court_category(text: str) -> bool:
    lowered = text.lower()
    serious_markers = (
        "семейно-бытов",
        "бытов",
        "насили",
        "побо",
        "уголов",
        "террор",
        "экстрем",
        "статья 73",
        "хулиган",
        "противоправные действия",
        # уголовные составы, существенные для комплаенса
        "мошенничеств",
        "статья 190",
        "ст. 190",
        "хищени",
        "растрат",
        "присвоени",
        "кража",
        "грабёж",
        "грабеж",
        "разбой",
        "убийств",
        "взятк",
        "коррупц",
        "легализац",
        "отмывани",
        "наркот",
        "контрабанд",
        "уклонение от уплаты",
    )
    return any(marker in lowered for marker in serious_markers)


def _is_conviction(case: dict[str, Any]) -> bool:
    """Дело с обвинительным приговором / признанием вины — существенный факт."""
    text = " ".join(
        str(case.get(k) or "") for k in ("result", "status")
    ).lower()
    return any(
        m in text
        for m in ("обвинительный приговор", "признан виновн", "осужд", "приговор")
    )


def _is_unresolved_case(case: dict[str, Any]) -> bool:
    text = " ".join(
        str(case.get(k) or "")
        for k in ("result", "status")
    ).lower()
    unresolved_markers = ("не заверш", "в производстве", "рассматрива", "pending")
    return any(marker in text for marker in unresolved_markers)


def _compact_role(resolved: dict[str, Any]) -> str:
    """Краткая роль для таблицы: при расхождении — пометка «сверить роль»
    (полное пояснение остаётся в блоке «Найденные факты»)."""
    if resolved["has_discrepancy"]:
        if resolved["party_list_role"] and resolved["party_list_role"] != resolved["adata_role"]:
            return f"{resolved['adata_role']} → {resolved['party_list_role']}? (сверить)"
        return f"{resolved['adata_role']} (сверить роль)"
    return resolved["display_role"]


def _collect_court_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    company_name = row.get("company_name") or "Компания"
    rows: list[dict[str, Any]] = []

    def _company_row(case: dict) -> dict[str, Any]:
        """Строка таблицы для дела компании — роль согласована со списками сторон."""
        category = case.get("category") or case.get("type") or "—"
        resolved = _resolve_person_case_role(case, company_name)
        is_defendant = (
            resolved["adata_role"] == "Ответчик"
            or resolved["party_list_role"] == "Ответчик"
        )
        return {
            "person_entity": _short_text(company_name, max_len=46),
            "role_in_case": _compact_role(resolved),
            "category": _short_text(category, max_len=70),
            "result": _short_text(case.get("result") or case.get("status"), max_len=48),
            "date": _short_text(case.get("date"), max_len=24),
            "source_links": _count_case_source_links(case),
            "is_top_officer": False,
            "is_defendant": is_defendant,
            "has_role_discrepancy": resolved["has_discrepancy"],
            "party_list_role": resolved["party_list_role"],
            "is_serious": _is_serious_court_category(str(category)) or _is_conviction(case),
            "is_unresolved": _is_unresolved_case(case),
            "contract_tier": _contract_relevance_tier(
                case, company_name, person_role="компания"
            ),
        }

    company_courts = enrichment.get("courts") or {}
    for case in (company_courts.get("cases") or []):
        if not isinstance(case, dict) or _should_skip_case_for_report(case):
            continue
        if _contract_relevance_tier(case, company_name, person_role="компания") == "noise":
            continue
        rows.append(_company_row(case))

    company_detailed = enriched.get("companyCourtCases")
    if isinstance(company_detailed, list):
        for case in company_detailed:
            if not isinstance(case, dict) or _should_skip_case_for_report(case):
                continue
            if _contract_relevance_tier(case, company_name, person_role="компания") == "noise":
                continue
            rows.append(_company_row(case))

    meta = enriched.get("individualCourtsMeta")
    individual_meta = meta if isinstance(meta, dict) else {}
    individual_courts = enriched.get("individualCourts")
    if isinstance(individual_courts, dict):
        for iin, cases in individual_courts.items():
            if not isinstance(cases, list):
                continue
            person_meta = individual_meta.get(iin) if isinstance(individual_meta.get(iin), dict) else {}
            person_name = str(person_meta.get("name") or iin)
            person_role = str(person_meta.get("role") or "")
            is_top_officer = any(
                marker in person_role.lower() for marker in ("директор", "руковод")
            )
            for case in cases:
                if not isinstance(case, dict) or _should_skip_case_for_report(case):
                    continue
                resolved = _resolve_person_case_role(case, person_name)
                category = case.get("category") or case.get("type") or "—"
                tier = _contract_relevance_tier(
                    case, person_name, person_role=person_role
                )
                if tier == "noise":
                    continue
                row_item = {
                    "person_entity": _short_text(person_name, max_len=46),
                    "role_in_case": _compact_role(resolved),
                    "category": _short_text(category, max_len=70),
                    "result": _short_text(case.get("result") or case.get("status"), max_len=48),
                    "date": _short_text(case.get("date"), max_len=24),
                    "source_links": _count_case_source_links(case),
                    "is_top_officer": is_top_officer,
                    "is_defendant": resolved["adata_role"] == "Ответчик",
                    "has_role_discrepancy": resolved["has_discrepancy"],
                    "party_list_role": resolved["party_list_role"],
                    "is_serious": _is_serious_court_category(str(category)) or _is_conviction(case),
                    "is_unresolved": _is_unresolved_case(case),
                    "contract_tier": tier,
                }
                rows.append(row_item)
    return rows


def _court_row_risk_score(item: dict[str, Any]) -> int:
    tier = item.get("contract_tier") or "neutral"
    base = {"red": 12, "yellow": 6, "neutral": 2, "noise": 0}.get(tier, 0)
    if item.get("is_top_officer"):
        base += 2
    if item.get("is_unresolved"):
        base += 1
    return base


def _format_courts_table_block(row: dict[str, Any], *, max_rows: int = 8) -> str:
    """Deterministic markdown table (top cases by risk score)."""
    rows = _collect_court_rows(row)
    company_name = row.get("company_name") or "Компания"
    if not rows:
        return "Судебные дела по компании и связанным лицам не обнаружены."

    rows_sorted = sorted(rows, key=_court_row_risk_score, reverse=True)
    shown = rows_sorted[:max_rows]
    hidden_count = max(0, len(rows_sorted) - len(shown))
    total_cases = len(rows_sorted)
    defendant_count = sum(1 for r in rows_sorted if r.get("is_defendant"))
    discrepancy_count = sum(1 for r in rows_sorted if r.get("has_role_discrepancy"))
    serious_count = sum(1 for r in rows_sorted if r.get("is_serious"))

    lines = [
        f"Кейс: {company_name}. Судебных записей: {total_cases}.",
        (
            f"Сводка: ответчик (Adata) {defendant_count}, "
            f"расхождение role/список сторон {discrepancy_count}, "
            f"серьёзные категории {serious_count}."
        ),
        "",
        "| Person/Entity | Роль в деле | Категория/статья | Результат | Дата | Source link count |",
        "|---|---|---|---|---|---:|",
    ]
    for item in shown:
        lines.append(
            "| "
            + " | ".join(
                [
                    _short_text(item.get("person_entity"), max_len=46).replace("|", "/"),
                    _short_text(item.get("role_in_case"), max_len=52).replace("|", "/"),
                    _short_text(item.get("category"), max_len=70).replace("|", "/"),
                    _short_text(item.get("result"), max_len=48).replace("|", "/"),
                    _short_text(item.get("date"), max_len=18).replace("|", "/"),
                    str(item.get("source_links") or 0),
                ]
            )
            + " |"
        )
    if hidden_count > 0:
        lines.append("")
        lines.append(f"Прочее: {hidden_count} дел (см. полный контекст в аналитике).")
    return "\n".join(lines)


def _sanitize_llm_text(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text)
    return re.sub(r"<[^>]+>", "", text)


def _split_sentences(text: str, *, limit: int = 10) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip(" -\t") for p in parts if p.strip()][:limit]


def _is_unstructured_plain_text(text: str) -> bool:
    if not text.strip():
        return True
    has_md = bool(re.search(r"(^|\n)\s*(#{1,4}\s|[-*]\s|\d+\.\s)", text))
    long_line = any(len(line) > 260 for line in text.splitlines() if line.strip())
    return not has_md or long_line


def _make_readable_markdown(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return MISSING
    if not _is_unstructured_plain_text(stripped):
        return stripped
    sentences = _split_sentences(stripped, limit=8)
    if not sentences:
        return stripped
    lines = ["### Ключевые наблюдения"]
    for sentence in sentences:
        lines.append(f"- {sentence[:240]}")
    return "\n".join(lines)


def _is_tree_node_line(line: str) -> bool:
    """Return True for affiliate-tree bullet lines like '**L0** Company | БИН `...`'."""
    return bool(re.search(r"\*\*L\d+\*\*", line)) or (
        "БИН" in line and "`" in line
    )


_FINDING_SKIP_PREFIXES = (
    "компания:",
    "бин:",
    "директор:",
    "уровень риска",
    "балл:",
    "оценка",
    "снимок",
    "источники",
    "данные:",
)


def _extract_key_findings(text: str, *, max_items: int = 2) -> list[str]:
    """Извлекает только содержательные выводы, пропуская технические строки."""
    findings: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### Найденные факты"):
            break
        if line.startswith(("- ", "* ")):
            candidate = line[2:].strip()
            if not candidate or re.match(r"^1\.?\s*$", candidate):
                continue
            lower = candidate.lower()
            if any(lower.startswith(p) for p in _FINDING_SKIP_PREFIXES):
                continue
            if _is_tree_node_line(candidate):
                continue
            if _line_mentions_courts(candidate) and not _line_mentions_sanctions(candidate):
                continue
            if len(candidate) < 25:
                continue
            findings.append(candidate[:200])
        elif line and not line.startswith("#") and len(line) > 40 and not _is_tree_node_line(line):
            lower = line.lower()
            if any(lower.startswith(p) for p in _FINDING_SKIP_PREFIXES):
                continue
            findings.append(line[:200])
        if len(findings) >= max_items:
            break
    if findings:
        return findings[:max_items]
    return _split_sentences(text, limit=max_items)


def _append_facts_block(section: str, text: str) -> str:
    """Гарантировать наличие блока ### Найденные факты, без выводов/флагов/действий."""
    normalized = text.strip()
    if "### Найденные факты" in normalized:
        return normalized
    findings = _extract_key_findings(normalized, max_items=5)
    block_lines = ["### Найденные факты"]
    if findings:
        for item in findings:
            block_lines.append(f"- {item}")
    else:
        block_lines.append("- Фактов по разделу не выявлено.")
    return f"{normalized}\n\n" + "\n".join(block_lines)


def _normalize_section_output(section: str, text: str) -> str:
    if section == "sanctions":
        return _normalize_sanctions_output(text)
    base = _sanitize_llm_text(text or "").strip() or MISSING
    if section in ("courts", "structure"):
        if "### Досье" in base or "### Найденные факты" in base:
            return base
        return _normalize_llm_conclusion(section, base)
    readable = _make_readable_markdown(base)
    return _append_facts_block(section, readable)


def _adata_company_link(bin_value: Any) -> str:
    """URL страницы компании на Adata по БИН (или пусто)."""
    from app.services.adata.client import adata_company_url

    return adata_company_url(bin_value) or ""


def _fact(label: str, text: str, *, url: str | None = None) -> str:
    """Строка факта: [Источник] текст — ссылка (если есть)."""
    suffix = f" — [источник]({url})" if url else ""
    return f"- [{label}] {text}{suffix}"


# ─── Профили физлиц (директор + учредители) ─────────────────────────────────

def _collect_individual_flags(enriched: dict[str, Any]) -> list[dict[str, Any]]:
    """Структурированные флаги физлиц из individualProfiles (Adata individual/info).

    По каждому ИИН: имя, возраст, жив ли, PEP, критические/прочие флаги, счётчики дел.
    """
    profiles = enriched.get("individualProfiles") or {}
    result: list[dict[str, Any]] = []
    if not isinstance(profiles, dict):
        return result
    for p_iin, prof in profiles.items():
        if not isinstance(prof, dict):
            continue
        basic = prof.get("basicFl") or {}
        reliability = prof.get("reliabilityFl") or {}
        critical: list[str] = []
        if reliability.get("terrorist"):
            critical.append("в списке террористов")
        if reliability.get("terrorism_involved"):
            critical.append("причастен к терроризму")
        if reliability.get("pedophile"):
            critical.append("в реестре педофилов")
        if reliability.get("missing"):
            critical.append("в розыске (пропавший без вести)")
        if reliability.get("citizen_hiding_from_investigation"):
            critical.append("скрывается от следствия")
        other: list[str] = []
        if reliability.get("enforcement_debt"):
            other.append("долг по исполнительному производству")
        if reliability.get("ban_leaving"):
            ban_sum = reliability.get("ban_leaving_sum", 0) or 0
            other.append(f"запрет на выезд (сумма {ban_sum:,.0f} тг)".replace(",", " "))
        if reliability.get("alimony_payer"):
            other.append("задолженность по алиментам")
        tax_debt = reliability.get("tax_debt") or 0
        if isinstance(tax_debt, (int, float)) and tax_debt > 0:
            other.append(f"налоговый долг {tax_debt:,.0f} тг".replace(",", " "))
        court = prof.get("courtCaseFl") or {}
        result.append(
            {
                "iin": str(p_iin),
                "name": _clean_person_display_name(basic.get("name") or f"ИИН {p_iin}"),
                "age": basic.get("age"),
                "alive": basic.get("alive"),
                "pep": bool(basic.get("is_public_official")),
                "critical_flags": critical,
                "other_flags": other,
                "courts": {
                    "civil": int(court.get("total_civil_count") or 0),
                    "criminal": int(court.get("total_criminal_count") or 0),
                    "admin": int(court.get("total_administrative_count") or 0),
                },
            }
        )
    return result


def _format_individual_profile_line(item: dict[str, Any]) -> str:
    """Одна строка профиля физлица для раздела «Физические лица»."""
    parts = [f"**{item['name']}** (ИИН {item['iin']})"]
    if item.get("age"):
        parts.append(f"{item['age']} лет")
    if item.get("alive") is False:
        parts.append("умер")
    if item.get("pep"):
        parts.append("ПДЛ (публичное должностное лицо)")
    line = f"- {' · '.join(parts)}"
    flags = list(item.get("critical_flags") or []) + list(item.get("other_flags") or [])
    line += f"\n  - Флаги: {'; '.join(flags) if flags else 'нет'}"
    c = item.get("courts") or {}
    total = c.get("civil", 0) + c.get("criminal", 0) + c.get("admin", 0)
    if total:
        line += (
            f"\n  - Дела (счётчик Adata): гражданских {c['civil']}, "
            f"уголовных {c['criminal']}, административных {c['admin']}"
        )
    return line


# ─── Санкционные связи ──────────────────────────────────────────────────────

def _describe_sanction_link(name: str, enriched: dict[str, Any]) -> str:
    """Как связанное лицо связано с компанией: доля (UBO) / через директора/учредителя."""
    name_key = _normalize_person_name_key(name)
    parts: list[str] = []
    for b in enriched.get("beneficiary") or []:
        if isinstance(b, dict) and _normalize_person_name_key(
            b.get("name") or b.get("short_name")
        ) == name_key:
            share = b.get("share") or b.get("ownershipShare")
            if _is_populated(share):
                parts.append(f"бенефициар, доля {share}")
            break
    rel = enriched.get("relationExtended") or {}
    if isinstance(rel, dict):
        head = rel.get("affiliation_by_head") or rel.get("affiliationByHead") or []
        founder = rel.get("affiliation_by_founder") or rel.get("affiliationByFounder") or []
        if any(
            isinstance(a, dict) and _normalize_person_name_key(a.get("name")) == name_key
            for a in (head if isinstance(head, list) else [])
        ):
            parts.append("связь через директора")
        if any(
            isinstance(a, dict) and _normalize_person_name_key(a.get("name")) == name_key
            for a in (founder if isinstance(founder, list) else [])
        ):
            parts.append("связь через учредителя")
    return "; ".join(parts)


def _collect_sanctioned_related(
    enriched: dict[str, Any], *, exclude: frozenset[str] = frozenset()
) -> tuple[list[dict], int]:
    """Связанные лица под санкциями/в списке наблюдения из lsegExtended.

    `exclude` — нормализованные ключи/имена/БИН проверяемой компании: её собственные
    совпадения раскрыты в блоке компании, в «связанных лицах» их дублировать не нужно.

    Возвращает (список_с_совпадениями, всего_проверено).
    """
    ext = enriched.get("lsegExtended") or {}
    flagged: list[dict] = []
    total = 0
    if isinstance(ext, dict):
        for key, entity in ext.items():
            if not isinstance(entity, dict):
                continue
            ident = {
                str(key).strip().lower(),
                _normalize_person_name_key(entity.get("name")),
                str(entity.get("iinBin") or entity.get("bin") or "").strip().lower(),
            }
            if ident & exclude:
                continue
            total += 1
            if entity.get("isOnSanctionList") or entity.get("hits"):
                flagged.append({**entity, "_key": key})
    return flagged, total


def _company_identity_keys(row: dict[str, Any]) -> frozenset[str]:
    """Нормализованные идентификаторы проверяемой компании (имя + БИН)."""
    return frozenset(
        k
        for k in (
            _normalize_person_name_key(row.get("company_name")),
            str(row.get("iin") or "").strip().lower(),
        )
        if k
    )


# ─── Профили аффилиатов L1 (Adata) ──────────────────────────────────────────

def _affiliate_tree_names(enriched: dict[str, Any]) -> dict[str, str]:
    """Карта БИН → название из дерева аффилиатов."""
    names: dict[str, str] = {}
    root = (enriched.get("affiliateTree") or {}).get("root")

    def _walk(node: dict) -> None:
        b = str(node.get("iinBin") or "").strip()
        if b and node.get("name"):
            names.setdefault(b, str(node.get("name")))
        for ch in node.get("children") or []:
            if isinstance(ch, dict):
                _walk(ch)

    if isinstance(root, dict):
        _walk(root)
    return names


def _collect_affiliate_profiles(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Профили L1-аффилиатов из affiliateProfiles (Adata): суды, налоги, флаги."""
    enriched = row.get("enriched_data") or {}
    profiles = enriched.get("affiliateProfiles") or {}
    if not isinstance(profiles, dict):
        return []
    names = _affiliate_tree_names(enriched)
    result: list[dict[str, Any]] = []
    for bin_val, prof in profiles.items():
        if not isinstance(prof, dict):
            continue
        courts = prof.get("courts") or {}
        taxes = prof.get("taxes") or {}
        debt = taxes.get("debt") or 0
        result.append(
            {
                "bin": str(bin_val),
                "name": names.get(str(bin_val)) or prof.get("name") or f"БИН {bin_val}",
                "director": _clean_person_display_name(prof.get("director"))
                if _is_populated(prof.get("director")) else None,
                "active_courts": int(courts.get("activeCases") or 0),
                "completed_courts": int(courts.get("completedCases") or 0),
                "tax_status": _ru_tax_status(taxes.get("status")),
                "tax_debt": debt if isinstance(debt, (int, float)) else 0,
                "risk_flags": prof.get("riskFlags") or [],
                "status": prof.get("operatingStatus"),
            }
        )
    return result


def _affiliate_has_signal(aff: dict[str, Any]) -> bool:
    return bool(aff["active_courts"] > 0 or (aff["tax_debt"] or 0) > 0)


# ─── Trustworthy-Plus: реестровые признаки риска ────────────────────────────

_TRUSTWORTHY_FLAGS: dict[str, str] = {
    "rehabilitation_proceedings": "процедура реабилитации",
    "rehabilitation_proceedings_admin_approval": "реабилитация (адм. утверждение)",
    "bankruptcy_initiation_and_manager_creditor_claims": "инициирование банкротства",
    "bankruptcy_and_liquidation_initiation_notices": "уведомления о банкротстве/ликвидации",
    "creditors_meeting_in_bankruptcy": "собрание кредиторов (банкротство)",
    "creditor_meeting_announcements_for_rehab": "объявления о собрании кредиторов (реабилитация)",
    "in_seized_property_sales_registry": "в реестре продажи арестованного имущества",
    "same_director_problem_company": "директор связан с проблемной компанией",
    "executive_inscription": "исполнительная надпись",
}


def _collect_trustworthy_flags(enriched: dict[str, Any]) -> list[str]:
    """Существенные реестровые признаки из trustworthyPlus (банкротство, арест, массовый адрес…)."""
    tp = enriched.get("trustworthyPlus") or {}
    if not isinstance(tp, dict):
        return []
    flags: list[str] = []
    ma = tp.get("mass_address")
    if isinstance(ma, (int, float)) and ma > 1:
        flags.append(f"массовый адрес регистрации ({int(ma)} компаний по тому же адресу)")
    for key, label in _TRUSTWORTHY_FLAGS.items():
        v = tp.get(key)
        if v in (None, False, 0, "", [], {}):
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            flags.append(f"{label}: {int(v)}")
        else:
            flags.append(label)
    return flags


# ─── Снимок (факт-дашборд) ──────────────────────────────────────────────────

def _build_fact_snapshot(row: dict[str, Any]) -> str:
    """Таблица состояний для быстрого триажа (факты, без оценок риска)."""
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    info = enrichment.get("companyInfo") or {}
    lseg = enriched.get("lseg") or {}
    san = lseg.get("sanctions") or {}
    pep = lseg.get("pep") or {}
    adata_san = enrichment.get("sanctions") or {}

    # Санкции компании
    if san.get("isOnList") or adata_san.get("isOnList"):
        company_san = "есть совпадения"
    else:
        hits = san.get("hits") or []
        company_san = "совпадений нет" if not hits else f"проверить ({len(hits)} совпад.)"

    # PEP руководства
    if pep.get("isHit"):
        names = [
            h.get("primaryName", "—") for h in (pep.get("individuals") or [])[:2]
        ]
        pep_state = "выявлен: " + ", ".join(n for n in names if n) if names else "выявлен"
    else:
        pep_state = "не выявлен"

    # Связанные лица под санкциями (без самой проверяемой компании)
    flagged, total_related = _collect_sanctioned_related(
        enriched, exclude=_company_identity_keys(row)
    )
    if total_related:
        related_state = (
            f"{len(flagged)} из {total_related}" if flagged else f"0 из {total_related}"
        )
    else:
        related_state = "скрининг не выполнялся"

    # Критические статусы физлиц
    individuals = _collect_individual_flags(enriched)
    crit_people = [p for p in individuals if p["critical_flags"] or p["alive"] is False]
    if crit_people:
        crit_state = "; ".join(
            f"{p['name']} — {', '.join(p['critical_flags'] or ['умер'])}"
            for p in crit_people[:3]
        )
    elif individuals:
        crit_state = "не выявлено"
    else:
        crit_state = "проверка не проводилась"

    # Суды (по компании и связанным лицам)
    court_rows = _collect_court_rows(row)
    defendant_n = sum(1 for r in court_rows if r.get("is_defendant"))
    serious_n = sum(1 for r in court_rows if r.get("is_serious"))
    courts_state = f"ответчик {defendant_n}, серьёзные {serious_n} (всего записей {len(court_rows)})"

    # Налоговая задолженность
    taxes = enrichment.get("taxes") or {}
    debt = taxes.get("debt")
    if debt is None:
        tax_state = "нет данных"
    elif debt and debt > 0:
        tax_state = f"{debt:,.0f} тг".replace(",", " ")
    else:
        tax_state = "нет задолженности"

    # Аффилиаты L1 (Adata профили): суды / налоговый долг
    aff_profiles = _collect_affiliate_profiles(row)
    if aff_profiles:
        aff_courts = sum(1 for a in aff_profiles if a["active_courts"] > 0)
        aff_debt = sum(1 for a in aff_profiles if (a["tax_debt"] or 0) > 0)
        aff_state = (
            f"проверено {len(aff_profiles)}: с активными судами {aff_courts}, "
            f"с налоговым долгом {aff_debt}"
        )
    else:
        aff_state = "профили не загружены"

    # Реестровые признаки (банкротство/арест/массовый адрес)
    tw_flags = _collect_trustworthy_flags(enriched)
    registry_state = "; ".join(tw_flags) if tw_flags else "не выявлено"

    # Глубина проверки
    tree = enriched.get("affiliateTree") or {}
    nodes = tree.get("nodesCount", 0) if isinstance(tree, dict) else 0
    depth_state = (
        f"физлиц проверено {len(individuals)}, узлов в дереве {nodes}"
    )

    status_ru = info.get("operatingStatus") if _is_populated(info.get("operatingStatus")) else "—"

    lines = [
        "| Параметр | Состояние |",
        "|---|---|",
        f"| Компания | {row.get('company_name') or MISSING} |",
        f"| БИН | {row.get('iin') or MISSING} |",
        f"| Статус | {status_ru} |",
        f"| Директор | {_clean_person_display_name(info.get('director'))} |",
        f"| Санкции компании | {company_san} |",
        f"| PEP руководства | {pep_state} |",
        f"| Связанные лица под санкциями | {related_state} |",
        f"| Критические статусы физлиц | {crit_state} |",
        f"| Суды | {courts_state} |",
        f"| Налоговая задолженность | {tax_state} |",
        f"| Аффилиаты L1 (Adata) | {aff_state} |",
        f"| Реестровые признаки | {registry_state} |",
        f"| Глубина проверки | {depth_state} |",
    ]
    return "\n".join(lines)


# ─── Существенные факты ─────────────────────────────────────────────────────

def _build_material_facts_block(row: dict[str, Any]) -> str:
    """Все существенные факты в одном месте, сгруппированы по типу (без оценок)."""
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    company_name = row.get("company_name") or MISSING
    main_bin = row.get("iin")
    groups: list[tuple[str, list[str]]] = []

    # Санкции и PEP
    san_facts: list[str] = []
    lseg = enriched.get("lseg") or {}
    company_hits = (lseg.get("sanctions") or {}).get("hits") or []
    if (lseg.get("sanctions") or {}).get("isOnList") or company_hits:
        for h in company_hits[:3]:
            san_facts.append(
                _fact("LSEG", f"{company_name}: {_lseg_hit_summary(h)}", url=_adata_company_link(main_bin) or None)
            )
        if not company_hits and (lseg.get("sanctions") or {}).get("isOnList"):
            san_facts.append(_fact("LSEG", f"{company_name}: в санкционных списках WC1"))
    adata_san = enrichment.get("sanctions") or {}
    if adata_san.get("isOnList"):
        lists = ", ".join(str(x) for x in (adata_san.get("lists") or [])[:5])
        san_facts.append(_fact("Adata", f"{company_name}: санкции/риски ({lists or 'список не указан'})"))
    for h in (lseg.get("pep") or {}).get("individuals", [])[:3]:
        name = h.get("primaryName", "—")
        strength = _ru_match_strength(h.get("matchStrength"))
        sp = f" (совпадение {strength})" if strength and strength != "—" else ""
        san_facts.append(_fact("LSEG", f"PEP: {name}{sp}"))
    flagged, _total = _collect_sanctioned_related(
        enriched, exclude=_company_identity_keys(row)
    )
    for entity in flagged[:10]:
        name = entity.get("name") or entity.get("_key")
        role = entity.get("role") or "связанное лицо"
        country = entity.get("country") or "—"
        status = "под санкциями" if entity.get("isOnSanctionList") else "совпадение в WC1"
        link = _describe_sanction_link(str(name), enriched)
        link_part = f"; {link}" if link else ""
        san_facts.append(
            _fact("LSEG", f"{name} ({role}, {country}): {status}{link_part}")
        )
    if san_facts:
        groups.append(("Санкции и PEP", san_facts))

    # Критические статусы физлиц
    people_facts: list[str] = []
    for p in _collect_individual_flags(enriched):
        signals: list[str] = list(p["critical_flags"]) + list(p["other_flags"])
        if p["alive"] is False:
            signals.insert(0, "умер")
        if not signals:
            continue
        url = _adata_company_link(p["iin"]) or None
        people_facts.append(_fact("Adata", f"{p['name']} (ИИН {p['iin']}): {'; '.join(signals)}", url=url))
    if people_facts:
        groups.append(("Критические статусы физлиц", people_facts))

    # Судебные
    court_facts: list[str] = []
    for line in _build_courts_fact_lines(row, material_only=True)[:12]:
        court_facts.append(line)
    if court_facts:
        groups.append(("Судебные", court_facts))

    # Налоги
    tax_facts: list[str] = []
    taxes = enrichment.get("taxes") or {}
    debt = taxes.get("debt")
    if isinstance(debt, (int, float)) and debt > 0:
        tax_facts.append(
            _fact("Adata", f"{company_name}: налоговая задолженность {debt:,.0f} тг".replace(",", " "))
        )
    if tax_facts:
        groups.append(("Налоги", tax_facts))

    # Аффилиаты L1 (Adata): суды / налоговый долг
    aff_facts: list[str] = []
    for aff in _collect_affiliate_profiles(row):
        if not _affiliate_has_signal(aff):
            continue
        bits: list[str] = []
        if aff["active_courts"] > 0:
            bits.append(f"активных судебных дел {aff['active_courts']}")
        if (aff["tax_debt"] or 0) > 0:
            bits.append(f"налоговая задолженность {aff['tax_debt']:,.0f} тг".replace(",", " "))
        aff_facts.append(
            _fact(
                "Adata",
                f"Аффилиат {aff['name']} (БИН {aff['bin']}): {'; '.join(bits)}",
                url=_adata_company_link(aff["bin"]) or None,
            )
        )
    if aff_facts:
        groups.append(("Аффилиаты (Adata, L1)", aff_facts))

    # Реестровые признаки (Trustworthy-Plus): банкротство, арест, массовый адрес…
    tw_flags = _collect_trustworthy_flags(enriched)
    if tw_flags:
        groups.append(
            ("Реестры и признаки",
             [_fact("Adata", f"{company_name}: {f}") for f in tw_flags])
        )

    if not groups:
        return "Существенных фактов не выявлено; проверенные позиции — без замечаний."

    out: list[str] = []
    for title, facts in groups:
        out.append(f"### {title}")
        out.extend(facts)
        out.append("")
    return "\n".join(out).strip()


# ─── Физические лица ────────────────────────────────────────────────────────

def _build_individuals_section(row: dict[str, Any]) -> str:
    """Раздел «Физические лица»: директор + учредители (флаги, счётчики дел)."""
    enriched = row.get("enriched_data") or {}
    individuals = _collect_individual_flags(enriched)
    if not individuals:
        return "Профили физлиц (директор/учредители) не загружены."
    lines: list[str] = []
    for item in individuals:
        lines.append(_format_individual_profile_line(item))
    return "\n".join(lines)


# ─── Карта покрытия данных ──────────────────────────────────────────────────

_COVERAGE_LABELS: list[tuple[str, str]] = [
    ("enrichment", "Adata: профиль компании"),
    ("lseg", "LSEG: компания и директор"),
    ("lsegExtended", "LSEG: аффилиаты/нерезиденты"),
    ("companyCourtCases", "Adata: судебные дела компании"),
    ("individualCourts", "Adata: персональные суды (ИИН)"),
    ("individualProfiles", "Adata: профили физлиц (флаги)"),
    ("affiliateProfiles", "Adata: профили аффилиатов L1 (суды/налоги)"),
    ("beneficiary", "Adata: бенефициары (UBO)"),
    ("nonResidents", "Adata: нерезиденты"),
    ("relationExtended", "Adata: связи через директора/учредителей"),
    ("trustworthyPlus", "Adata: реестры/признаки (Trustworthy-Plus)"),
    ("affiliateTree", "Дерево аффилиатов"),
]


def _build_coverage_map(row: dict[str, Any]) -> str:
    """Что проверено / каких данных нет — прозрачность полноты для аудита."""
    enriched = row.get("enriched_data") or {}
    checked: list[str] = []
    missing: list[str] = []
    for key, label in _COVERAGE_LABELS:
        val = enriched.get(key)
        if key == "nonResidents" and isinstance(val, dict):
            ok = _is_populated(val.get("data"))
        else:
            ok = _is_populated(val)
        (checked if ok else missing).append(label)
    lines = ["**Проверено:**"]
    lines.extend(f"- {c}" for c in checked) if checked else lines.append("- —")
    lines.append("\n**Данные отсутствуют / не загружены:**")
    if missing:
        lines.extend(f"- {m}" for m in missing)
    else:
        lines.append("- — (все источники получены)")
    return "\n".join(lines)


def _assemble_report(row: dict[str, Any], summary_block: str) -> str:
    """Финальная сборка отчёта максимальной ценности (детерминированно + 1 LLM-резюме)."""
    company_name = row.get("company_name") or MISSING
    iin = row.get("iin") or MISSING

    snapshot = _build_fact_snapshot(row)
    material = _build_material_facts_block(row)
    sanctions = _build_sanctions_section(row)
    courts = _build_courts_section(row)
    structure = _build_structure_section(row)
    individuals = _build_individuals_section(row)
    coverage = _build_coverage_map(row)

    summary_part = f"## Резюме\n{summary_block.strip()}\n\n" if summary_block.strip() else ""

    return (
        f"# Отчёт по контрагенту: {company_name} (БИН {iin})\n\n"
        f"## Снимок\n{snapshot}\n\n"
        f"{summary_part}"
        f"## Существенные факты\n{material}\n\n"
        f"## 1. Санкционный анализ\n{sanctions}\n\n"
        f"## 2. Судебные дела\n{courts}\n\n"
        f"## 3. Структура и бенефициары\n{structure}\n\n"
        f"## 4. Физические лица\n{individuals}\n\n"
        f"## Карта покрытия данных\n{coverage}\n"
    )


# ─── Детерминированные секции ───────────────────────────────────────────────

def _case_best_link(case: dict, fallback_bin: Any = None) -> str | None:
    """Лучшая ссылка по делу: документ дела, иначе страница компании Adata."""
    for doc in case.get("documents") or []:
        if isinstance(doc, dict) and (doc.get("doc_link") or doc.get("docLink")):
            return doc.get("doc_link") or doc.get("docLink")
    for ev in case.get("history") or []:
        for doc in ev.get("documents") or []:
            if isinstance(doc, dict) and (doc.get("doc_link") or doc.get("docLink")):
                return doc.get("doc_link") or doc.get("docLink")
    return _adata_company_link(fallback_bin) or None


def _court_fact_line(case: dict, entity: str, *, fallback_bin: Any = None) -> str | None:
    """Строка факта по одному делу с согласованной ролью и ссылкой."""
    if _should_skip_case_for_report(case):
        return None
    resolved = _resolve_person_case_role(case, entity)
    cat = case.get("category") or case.get("type") or "категория не указана"
    number = case.get("number") or "—"
    date = case.get("date") or "—"
    status = case.get("result") or case.get("status") or "—"
    text = (
        f"{entity}: {resolved['display_role']} по «{_short_text(cat, max_len=90)}» "
        f"· дело №{number} · {date} · {status}"
    )
    if resolved["has_discrepancy"]:
        defendants = case.get("defendants") or []
        participants = case.get("participants") or []
        if defendants:
            text += f" · ответчики: {', '.join(str(d) for d in defendants[:4])}"
        elif participants:
            text += f" · участники дела: {', '.join(str(p).strip() for p in participants[:4])}"
    return _fact("Adata", text, url=_case_best_link(case, fallback_bin))


def _build_courts_fact_lines(row: dict[str, Any], *, material_only: bool = False) -> list[str]:
    """Факты по судам: дела компании + индивидуальные дела (роли согласованы)."""
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    company_name = row.get("company_name") or "Компания"
    main_bin = row.get("iin")
    lines: list[str] = []

    def _keep(case: dict, entity: str, role_hint: str = "") -> bool:
        if not material_only:
            return True
        resolved = _resolve_person_case_role(case, entity)
        category = str(case.get("category") or case.get("type") or "")
        is_defendant = (
            resolved["adata_role"] == "Ответчик"
            or resolved["party_list_role"] == "Ответчик"
        )
        return bool(
            is_defendant
            or _is_serious_court_category(category)
            or _is_conviction(case)
            or resolved["has_discrepancy"]
        )

    company_cases: list[dict] = []
    for case in (enrichment.get("courts") or {}).get("cases") or []:
        if isinstance(case, dict):
            company_cases.append(case)
    detailed = enriched.get("companyCourtCases")
    if isinstance(detailed, list):
        company_cases.extend(c for c in detailed if isinstance(c, dict))
    for case in company_cases:
        if _should_skip_case_for_report(case) or not _keep(case, company_name):
            continue
        line = _court_fact_line(case, company_name, fallback_bin=main_bin)
        if line:
            lines.append(line)

    meta = enriched.get("individualCourtsMeta")
    individual_meta = meta if isinstance(meta, dict) else {}
    individual_courts = enriched.get("individualCourts")
    if isinstance(individual_courts, dict):
        for iin, cases in individual_courts.items():
            if not isinstance(cases, list):
                continue
            person_meta = (
                individual_meta.get(iin)
                if isinstance(individual_meta.get(iin), dict)
                else {}
            )
            person_name = str(person_meta.get("name") or iin)
            for case in cases:
                if not isinstance(case, dict):
                    continue
                if _should_skip_case_for_report(case) or not _keep(case, person_name):
                    continue
                line = _court_fact_line(case, person_name, fallback_bin=iin)
                if line:
                    lines.append(line)
    return lines


def _build_courts_section(row: dict[str, Any]) -> str:
    """Раздел «Судебные дела»: таблица + факты (детерминированно, без LLM)."""
    table = _format_courts_table_block(row)
    facts = _build_courts_fact_lines(row, material_only=False)
    if facts:
        body = "### Найденные факты\n" + "\n".join(facts)
    else:
        body = "### Найденные факты\n- Фактов по разделу не выявлено."
    return f"{table}\n\n{body}"


def _build_sanctions_section(row: dict[str, Any]) -> str:
    """Раздел «Санкционный анализ»: скрининг + связанные лица с цепочкой связи."""
    enriched = row.get("enriched_data") or {}
    facts_block = _build_sanctions_facts_block(row)
    flagged, _total = _collect_sanctioned_related(
        enriched, exclude=_company_identity_keys(row)
    )
    chain_lines: list[str] = []
    for entity in flagged[:15]:
        name = entity.get("name") or entity.get("_key")
        role = entity.get("role") or "связанное лицо"
        country = entity.get("country") or "—"
        status = "под санкциями" if entity.get("isOnSanctionList") else "совпадение в WC1"
        link = _describe_sanction_link(str(name), enriched)
        link_part = f"; {link}" if link else ""
        chain_lines.append(
            _fact("LSEG", f"{name} ({role}, {country}): {status}{link_part}")
        )
    if chain_lines:
        return f"{facts_block}\n\n### Связанные лица под санкциями\n" + "\n".join(chain_lines)
    return facts_block


def _build_structure_fact_lines(row: dict[str, Any]) -> list[str]:
    """Существенные структурные сигналы: аффилиаты с санкциями/PEP (без судов)."""
    enriched = row.get("enriched_data") or {}
    lines: list[str] = []
    for aff in _collect_affiliate_enrichments(enriched.get("affiliateTree"), max_depth=2):
        lseg = aff.get("lseg") or {}
        sig: list[str] = []
        if (aff.get("sanctions") or {}).get("isOnList"):
            sig.append("санкции Adata")
        if (lseg.get("sanctions") or {}).get("isOnList"):
            sig.append("санкции LSEG")
        if (lseg.get("pep") or {}).get("isHit"):
            sig.append("PEP")
        if sig:
            lines.append(
                _fact(
                    "Adata/LSEG",
                    f"Аффилиат {aff.get('name')} (БИН {aff.get('iinBin')}): {', '.join(sig)}",
                    url=_adata_company_link(aff.get("iinBin")) or None,
                )
            )
    return lines


def _build_affiliate_profiles_block(row: dict[str, Any]) -> str:
    """Профили L1-аффилиатов (Adata): директор, суды, налоги, флаги — по каждому."""
    profs = _collect_affiliate_profiles(row)
    if not profs:
        return ""
    lines = ["### Профили аффилиатов (Adata, L1)"]
    for a in sorted(profs, key=_affiliate_has_signal, reverse=True):
        link = _adata_company_link(a["bin"])
        head = f"- **{a['name']}** (БИН {a['bin']})"
        if link:
            head += f" — [источник]({link})"
        lines.append(head)
        det: list[str] = []
        if a["director"]:
            det.append(f"директор: {a['director']}")
        det.append(
            f"суды: активных {a['active_courts']}, завершённых {a['completed_courts']}"
        )
        tax = a["tax_status"] or "—"
        if (a["tax_debt"] or 0) > 0:
            debt_str = f"{a['tax_debt']:,.0f}".replace(",", " ")
            tax += f", долг {debt_str} тг"
        det.append(f"налоги: {tax}")
        if a["status"]:
            det.append(f"статус: {a['status']}")
        if a["risk_flags"]:
            det.append("флаги: " + "; ".join(str(f) for f in a["risk_flags"][:2]))
        lines.append("  - " + " · ".join(det))
    return "\n".join(lines)


def _build_relations_block(row: dict[str, Any]) -> str:
    """Сеть связей через директора/учредителей/компании (relationExtended)."""
    rel = (row.get("enriched_data") or {}).get("relationExtended") or {}
    if not isinstance(rel, dict):
        return ""

    def _fmt(items: Any, label: str) -> list[str]:
        rows: list[str] = []
        for a in (items if isinstance(items, list) else [])[:8]:
            if not isinstance(a, dict):
                continue
            nm = (
                a.get("name")
                or a.get("head_name")
                or a.get("founder_name")
                or a.get("company_name")
            )
            if not _is_populated(nm):
                continue
            comps = a.get("companies")
            extra = (
                f" — связанных компаний: {len(comps)}"
                if isinstance(comps, list) and comps
                else ""
            )
            rows.append(f"- {nm}{extra}")
        return ([f"**{label}:**"] + rows) if rows else []

    body: list[str] = []
    body += _fmt(rel.get("affiliation_by_head") or rel.get("affiliationByHead"), "По руководителю")
    body += _fmt(rel.get("affiliation_by_founder") or rel.get("affiliationByFounder"), "По учредителям")
    body += _fmt(rel.get("affiliation_by_company") or rel.get("affiliationByCompany"), "По компаниям")
    if not body:
        return ""
    return "### Связи через директора/учредителей\n" + "\n".join(body)


def _build_trustworthy_block(row: dict[str, Any]) -> str:
    """Реестровые признаки (банкротство/арест/массовый адрес) из trustworthyPlus."""
    flags = _collect_trustworthy_flags(row.get("enriched_data") or {})
    if not flags:
        return ""
    return "### Реестры и признаки (Trustworthy-Plus)\n" + "\n".join(
        f"- {f}" for f in flags
    )


def _build_structure_section(row: dict[str, Any]) -> str:
    """Раздел «Структура и бенефициары»: досье + аффилиаты L1 + связи + реестры."""
    parts = [_build_structure_dossiers_block(row)]
    for block in (
        _build_affiliate_profiles_block(row),
        _build_relations_block(row),
        _build_trustworthy_block(row),
    ):
        if block:
            parts.append(block)
    facts = _build_structure_fact_lines(row)
    if facts:
        parts.append("### Найденные факты\n" + "\n".join(facts))
    else:
        parts.append("### Найденные факты\n- Существенных структурных сигналов не выявлено.")
    return "\n\n".join(parts)


async def _call_llm_section(
    client: Any,
    section: str,
    context: str,
    company_name: str,
) -> str:
    system_prompt = _SECTION_PROMPTS[section]
    user_prompts = {
        "sanctions": (
            f"По фактам LSEG для «{company_name}» напиши ТОЛЬКО блок ### Найденные факты "
            f"(объективные факты по санкциям/PEP/WC1 с источником). Без судов, налогов, структуры. "
            f"Без выводов, флагов и действий."
        ),
        "courts": (
            f"По таблице и делам для «{company_name}» напиши только блок ### Найденные факты: "
            f"перечисли каждое дело фактически (роль Adata, категория/статья, № дела, дата, статус). "
            f"Без оценки тяжести, без флагов, без выводов и действий."
        ),
        "structure": (
            f"По досье компаний для «{company_name}» напиши только блок ### Найденные факты "
            f"(связи и факты по аффилиатам с источником). Без выводов, флагов и действий."
        ),
        "summary": f"Составь фактологическую сводку фактов для «{company_name}».",
    }
    response = await client.chat.completions.create(
        name=f"full_report_{section}",
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"{context}\n\n{user_prompts[section]}",
            },
        ],
        temperature=0.2,
        max_tokens=1000 if section == "summary" else 2800,
    )
    content = response.choices[0].message.content or ""
    if section == "summary":
        return _sanitize_llm_text(content)
    if section == "sanctions":
        return _normalize_sanctions_output(content)
    if section in ("courts", "structure"):
        return _normalize_llm_conclusion(section, content)
    return _normalize_section_output(section, content)


def _build_source_links_section(row: dict[str, Any]) -> str:
    """Markdown section with real source URLs (Adata pages + court doc links)."""
    from app.services.adata.client import adata_company_url

    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    info = enrichment.get("companyInfo") or {}

    adata_lines: list[str] = []
    seen: set[str] = set()

    def _add(name: str, bin_value: str | None, explicit_url: str | None = None) -> None:
        url = explicit_url or adata_company_url(bin_value)
        if not url or url in seen:
            return
        seen.add(url)
        label = name or (f"БИН {bin_value}" if bin_value else "Компания")
        adata_lines.append(f"- {label} — {url}")

    main_iin = row.get("iin")
    _add(row.get("company_name") or info.get("fullName") or "", main_iin, info.get("sourceLink"))
    for comp in (enrichment.get("affiliates") or {}).get("companies") or []:
        _add(str(comp.get("name") or ""), comp.get("iinBin") or comp.get("bin"))

    # Court-case document links (actual files on Adata CDN).
    doc_lines: list[str] = []
    seen_docs: set[str] = set()

    def _collect_docs(cases: Any) -> None:
        if not isinstance(cases, list):
            return
        for case in cases:
            if not isinstance(case, dict):
                continue
            number = str(case.get("number") or case.get("date") or "дело")
            for doc in case.get("documents") or []:
                link = isinstance(doc, dict) and (doc.get("doc_link") or doc.get("docLink"))
                if link and link not in seen_docs:
                    seen_docs.add(link)
                    doc_lines.append(f"- дело №{number} — {link}")

    _collect_docs(enriched.get("companyCourtCases"))
    for cases in (enriched.get("individualCourts") or {}).values():
        _collect_docs(cases)

    blocks: list[str] = []
    if adata_lines:
        blocks.append("**Adata (страницы компаний):**\n" + "\n".join(adata_lines))
    if doc_lines:
        blocks.append("**Документы судебных дел:**\n" + "\n".join(doc_lines[:20]))
    if enriched.get("lseg"):
        blocks.append(
            "**LSEG World-Check One:** закрытый санкционный скрининг — "
            "публичной ссылки нет, проверка фиксируется в журнале верификации."
        )

    if not blocks:
        return ""
    return "## Ссылки на источники\n\n" + "\n\n".join(blocks)


async def generate_full_report(case_id: str) -> str:
    """Generate and save full compliance report. Returns report text."""
    row = db.get_case(case_id)
    if row is None:
        raise ValueError(f"Case {case_id} not found")

    try:
        return await _generate_full_report_impl(case_id, row)
    except Exception:
        fresh_row = db.get_case(case_id)
        if fresh_row is not None:
            stale = fresh_row.get("enriched_data") or {}
            if isinstance(stale, dict) and stale.get("fullReportStatus") == "generating":
                stale = dict(stale)
                stale.pop("fullReportStatus", None)
                db.update_case(case_id, enriched_data=stale)
        raise


async def _generate_full_report_impl(case_id: str, row: dict[str, Any]) -> str:
    company_name = row.get("company_name", MISSING)
    enriched = row.get("enriched_data") or {}
    sources_list = _list_data_sources(enriched)
    append_case_event(
        case_id,
        provider="AI",
        action="full_report:start",
        subject={"type": "case", "value": case_id, "name": company_name},
        outcome={"status": "ok", "meta": {"availableBlocks": sources_list}},
    )

    # Детерминированная сборка из БД — мгновенно. Единственный LLM-вызов —
    # краткое резюме по существенным фактам (facts-only); если их нет, LLM не зовём.
    material = _build_material_facts_block(row)
    has_material = bool(
        material.strip()
        and not material.startswith("Существенных фактов не выявлено")
    )
    summary = ""

    if settings.openai_api_key and has_material:
        try:
            from app.services.ai.langfuse_setup import ai_trace, create_async_openai_client

            case_iin = str(row.get("iin") or "").strip()
            with ai_trace(name="full_report", iin=case_iin, case_id=case_id):
                client = create_async_openai_client()
                summary = await _call_llm_section(
                    client, "summary", material, company_name
                )
            append_case_event(
                case_id,
                provider="AI",
                action="full_report:section:summary",
                outcome={
                    "status": "ok",
                    "meta": {"mode": "llm", "availableBlocks": sources_list},
                },
            )
        except Exception as exc:
            logger.warning("OpenAI summary failed for %s: %s", case_id, exc)
            summary = ""
            append_case_event(
                case_id,
                provider="AI",
                action="full_report:section:summary",
                outcome={
                    "status": "error",
                    "meta": {"mode": "skipped", "availableBlocks": sources_list},
                    "message": str(exc)[:200],
                },
            )

    report = _assemble_report(row, summary)
    append_case_event(
        case_id,
        provider="AI",
        action="full_report:assembled",
        outcome={
            "status": "ok",
            "meta": {"mode": "deterministic", "availableBlocks": sources_list},
        },
    )

    # Real source URLs (Adata company pages + court document links).
    source_links = _build_source_links_section(row)
    if source_links:
        report = f"{report}\n\n{source_links}"

    # Auto-expand abbreviations: append a legend for every glossary term used.
    from app.services.glossary import glossary_legend_markdown

    legend = glossary_legend_markdown(report)
    if legend:
        report = f"{report}\n\n{legend}"

    # Reload fresh enriched data so the verification log events added during
    # section generation are not overwritten by the stale local `enriched` dict.
    fresh_row = db.get_case(case_id)
    save_enriched: dict = {}
    if fresh_row is not None:
        fresh_data = fresh_row.get("enriched_data") or {}
        save_enriched = fresh_data if isinstance(fresh_data, dict) else {}
    else:
        save_enriched = enriched

    save_enriched["fullReport"] = report
    save_enriched["fullReportGeneratedAt"] = datetime.now(timezone.utc).isoformat()
    tree_meta = save_enriched.get("affiliateTree") or {}
    if isinstance(tree_meta, dict) and tree_meta.get("builtAt"):
        save_enriched["fullReportTreeBuiltAt"] = tree_meta["builtAt"]
    save_enriched.pop("fullReportStatus", None)
    db.update_case(case_id, enriched_data=save_enriched)

    logger.info("Full report saved for case %s", case_id)
    append_case_event(
        case_id,
        provider="AI",
        action="full_report:saved",
        outcome={"status": "ok"},
    )
    return report
