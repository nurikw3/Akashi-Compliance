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
from app.services.affiliate_tree import normalize_bin
from app.services.verification_log import append_case_event

logger = logging.getLogger(__name__)

MISSING = "Данные отсутствуют"

_OFFICER_FOCUS = """
ЦЕЛЬ: текст для комплаенс-офицера, принимающего решение по контрагенту.
- Конкретика: ФИО/компания, роль в деле, статья или категория, почему важно или малозначимо.
- Запрещена «вода» без фактов («может повлиять на репутацию» без указания статьи/дела).
- Если данных мало — так и напиши; не выдумывай.
"""

_LLM_CONCLUSION_ONLY = """
Досье по компаниям УЖЕ в отчёте (код). Ты пишешь ТОЛЬКО итог.

Формат — один блок ### Вывод ИИ (3–5 пунктов), без длинных абзацев.
В конце: - Риск: green/yellow/red flag  и  - Действие: ...
"""

_COURTS_DEAL_POLICY = """
ПОЛИТИКА: что важно для подписания договора с контрагентом.

🔴 RED FLAG — эскалировать до сделки:
- Директор/руководитель КОМПАНИИ-КОНТРАГЕНТА — ОТВЕТЧИК по:
  ст.73 (семейно-бытовые), насилию, уголовным категориям, мошенничеству, хищению.

🟡 YELLOW — упомянуть, не отказ:
- Налоговое взыскание с физлица-директора.
- Договорной спор аффилированного юрлица (не директор).
- Исполнительное производство на крупную сумму.

⚪ ИГНОРИРОВАТЬ (не упоминать в выводе вообще):
- ДТП, ст.610, ПДД, нарушение ПДД, компенсация ущерба от ДТП.
- Участие третьей стороной.
- Сводные строки без конкретного дела («Г:0 У:0»).
- Административные штрафы водителю.

ФОРМАТ: только ### Вывод ИИ. Если red/yellow дел нет — одна строка «Судебных рисков для сделки не выявлено».
НЕ перечисляй нейтральные дела. НЕ используй слово «может» без факта.
"""

_SUMMARY_SECTION_EXCERPT_CHARS = 6000

_SYSTEM_PROMPT_SANCTIONS_CONCLUSION = f"""Ты — старший комплаенс-аналитик. Итог раздела «Санкционный анализ».
Блок фактов LSEG/PEP УЖЕ в отчёте (код). Пиши ТОЛЬКО:

### Краткое сведение
- Ключевой вывод: ... (только санкции/PEP/списки WC1)
- Риск: green flag | yellow flag | red flag
- Следующее действие: ...

ЗАПРЕЩЕНО упоминать: суды, иски, ответчик/истец, налоги, структуру, ДТП, скоринг courts.
{_OFFICER_FOCUS}"""

SYSTEM_PROMPT_SANCTIONS = _SYSTEM_PROMPT_SANCTIONS_CONCLUSION

SYSTEM_PROMPT_COURTS = f"""Ты — старший комплаенс-аналитик. Итог по разделу «Судебные дела» для офицера.
Таблица дел уже в отчёте. Пиши ТОЛЬКО блок ### Вывод ИИ.
{_COURTS_DEAL_POLICY}
{_OFFICER_FOCUS}"""

_STRUCTURE_POLICY = """
ПРАВИЛА (строго):
- Пиши ТОЛЬКО о том, что есть в досье в контексте. Нет данных — напиши «данные отсутствуют».
- НЕ выдумывай UBO, владельцев, связи, которых нет в контексте.
- НЕ используй слова «предположительно», «возможно связано», «вероятно».
- Аффилиаты с low-риском и без флагов — упомяни одной строкой, не разбирай.
- Фокус: кто РЕАЛЬНО несёт риск (санкции / суды / PEP / налоговый долг аффилиата).
"""

SYSTEM_PROMPT_STRUCTURE = f"""Ты — старший комплаенс-аналитик. Итог раздела «Структура и аффилиаты».
Досье по компаниям УЖЕ в отчёте (код). Пиши ТОЛЬКО блок:

### Вывод ИИ
- 3–5 пунктов: субъект + конкретный риск (санкции / суд / налог) + вес для решения.
- В конце: - Риск: green/yellow/red flag  и  - Действие: ...
{_STRUCTURE_POLICY}
{_OFFICER_FOCUS}"""

SYSTEM_PROMPT_SUMMARY = f"""Ты — старший комплаенс-аналитик. Executive Summary для решения по контрагенту.

ПРАВИЛА (строго):
1. Используй ТОЛЬКО факты из контекста. НЕ выдумывай.
2. НЕ используй «возможно», «может указывать», «предположительно» без конкретного факта.
3. ФОРМАТ — строго три блока на отдельных строках:

**Оценка:** [уровень риска, итоговый балл, одна фраза]

**Топ риски:**
- [источник: санкции/суды/структура] — [конкретный факт из контекста]
- [источник] — [факт]
- [источник] — [факт]

**Рекомендация:** [одобрить / дополнительная проверка / отказать] — [обоснование одной фразой]

4. Не пиши цифры 1) 2) 3) в строку. Каждый риск — отдельная строка с дефисом.
5. Максимум 3 риска. Если риска нет по разделу — не включай его.
{_OFFICER_FOCUS}"""

_SECTION_PROMPTS: dict[str, str] = {
    "sanctions": SYSTEM_PROMPT_SANCTIONS,
    "courts": SYSTEM_PROMPT_COURTS,
    "structure": SYSTEM_PROMPT_STRUCTURE,
    "summary": SYSTEM_PROMPT_SUMMARY,
}

_SECTION_MAX_CHARS: dict[str, int] = {
    "sanctions": 40_000,
    "courts": 40_000,
    "structure": 40_000,
    "summary": 20_000,
}


def _truncate_context(text: str, max_chars: int = 20000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[...данные усечены...]"


def _log_section(section: str, content: str) -> None:
    preview = content.replace("\n", " ")[:500]
    logger.info("full_report context [%s]: %s", section, preview)


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
        ("scoreBreakdown", "Скоринг (7 метрик)"),
        ("assessment", "Оценка риска (assessment)"),
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


def _format_director_companies(affiliates: dict[str, Any] | None) -> str:
    companies = (affiliates or {}).get("companies") or []
    individuals = (affiliates or {}).get("individuals") or []
    parts: list[str] = []
    for company in companies[:8]:
        parts.append(f"{company.get('name', '—')} ({company.get('iinBin', '—')})")
    for person in individuals[:3]:
        parts.append(f"{person.get('name', '—')} (ИИН {person.get('iin', '—')})")
    return "; ".join(parts) if parts else MISSING


def _lseg_hit_type(hit: dict) -> str:
    if hit.get("isSanction"):
        return "формальные санкции"
    if hit.get("isMaterialMatch"):
        return "watchlist"
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

    status = "🔴 под санкциями" if on_list else "⚠️ совпадение"
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
        parts.append("**Связанные лица под санкциями/в watchlist:**")
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
            pep_names.append(
                f"{h.get('primaryName', '—')} ({h.get('matchStrength', '')})"
            )
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
                        "riskLevel": row.get("risk_level"),
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


def _is_low_risk_affiliate(aff: dict) -> bool:
    risk = str(aff.get("riskLevel") or "").lower()
    courts = aff.get("courts") or {}
    has_courts = courts.get("activeCases", 0) > 0 or bool(courts.get("cases"))
    flags = aff.get("riskFlags") or []
    lseg = aff.get("lseg") or {}
    san = (lseg.get("sanctions") or {}) if lseg else {}
    sanctions = aff.get("sanctions") or {}
    pep = (lseg.get("pep") or {}) if lseg else {}
    return (
        risk == "low"
        and not has_courts
        and not flags
        and not san.get("isOnList")
        and not sanctions.get("isOnList")
        and not pep.get("isHit")
    )


def _format_affiliate_tree_compact(tree: dict, *, max_nodes: int = 15) -> str:
    lines: list[str] = []
    total = 0

    def _walk(node: dict, level: int) -> None:
        nonlocal total
        if total >= max_nodes:
            return
        name = node.get("name") or "—"
        iin_bin = node.get("iinBin") or "—"
        role = node.get("role") or ""
        indent = "  " * level
        role_part = f" | {role}" if role else ""
        lines.append(f"{indent}- **L{level}** {name} | БИН `{iin_bin}`{role_part}")
        total += 1
        for child in node.get("children") or []:
            if isinstance(child, dict) and total < max_nodes:
                _walk(child, level + 1)

    root = tree.get("root")
    if isinstance(root, dict):
        _walk(root, 0)
    nodes_count = tree.get("nodesCount", total)
    if nodes_count > total:
        lines.append(f"- *… ещё {nodes_count - total} узлов не показано*")
    return "\n".join(lines) if lines else MISSING


def _format_trustworthy_plus_summary(data: dict) -> str | None:
    lines: list[str] = []
    for k, v in data.items():
        if isinstance(v, (str, int, float, bool)) and v is not None and str(v).strip():
            lines.append(f"- {k}: {v}")
    return "\n".join(lines[:8]) if lines else None


def _format_court_case_line(case: dict) -> str:
    ai = case.get("aiAnalysis") or {}
    summary = ai.get("summary_ru") or case.get("status") or ""
    return f"- {case.get('type', '')}: {summary}"


def _dossier_case_link(case_id: str | None, *, label: str = "открыть досье") -> str:
    if case_id:
        return f" — [{label}](/cases/{case_id})"
    return ""


def _should_skip_case_for_report(case: dict) -> bool:
    """Сводные/пустые записи без предмета спора — не показывать в отчёте."""
    category = str(case.get("category") or case.get("type") or "")
    if re.search(r"г:\s*\d+\s+у:\s*\d+", category, re.IGNORECASE):
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

    role = _extract_case_role_by_parties(case, person_name)
    category = str(case.get("category") or case.get("type") or "")

    if role == "Третья сторона":
        return "noise"
    if _is_low_relevance_for_contract(category):
        return "noise"

    officer = _is_officer_role(person_role)
    if role == "Ответчик" and _is_serious_court_category(category):
        return "red"
    if role == "Ответчик" and officer and (
        "налог" in category.lower() or "задолж" in category.lower()
    ):
        return "yellow"
    if role == "Ответчик" and (
        "договор" in category.lower()
        or "сделк" in category.lower()
        or "спор" in category.lower()
    ):
        return "yellow" if not officer else "yellow"

    ai = case.get("aiAnalysis") or {}
    if role == "Ответчик" and str(ai.get("severity") or "").lower() in ("critical", "high"):
        if not _is_low_relevance_for_contract(category):
            return "red" if officer else "yellow"

    if role == "Ответчик":
        return "neutral"
    return "neutral"


def _tier_label_ru(tier: str) -> str:
    return {
        "red": "🔴 red flag для сделки",
        "yellow": "🟡 доп. проверка",
        "neutral": "нейтрально",
        "noise": "не мешает сделке",
    }.get(tier, tier)


def _severity_impact_label(
    case: dict,
    *,
    person_name: str,
    person_role: str = "",
) -> str:
    tier = _contract_relevance_tier(case, person_name, person_role=person_role)
    return _tier_label_ru(tier)


def _court_case_importance_score(
    case: dict,
    person_name: str,
    *,
    person_role: str = "",
) -> int:
    tier = _contract_relevance_tier(case, person_name, person_role=person_role)
    return {"red": 12, "yellow": 6, "neutral": 2, "noise": 0}.get(tier, 0)


def _summarize_courts_for_dossier(
    cases: list[dict],
    person_name: str,
    *,
    person_role: str = "",
) -> str:
    relevant = [c for c in cases if not _should_skip_case_for_report(c)]
    if not relevant:
        return "- Суды: не выявлено существенных дел"
    tiers = [
        _contract_relevance_tier(c, person_name, person_role=person_role) for c in relevant
    ]
    red_n = sum(1 for t in tiers if t == "red")
    yellow_n = sum(1 for t in tiers if t == "yellow")
    return (
        f"- Суды: записей {len(relevant)} · red flag {red_n} · "
        f"на доп. проверку {yellow_n}"
    )


def _format_court_case_dossier_bullet(
    case: dict,
    *,
    person_name: str,
    person_role: str = "",
) -> str:
    role = _extract_case_role_by_parties(case, person_name)
    category = case.get("category") or case.get("type") or "категория не указана"
    result = case.get("result") or case.get("status") or "—"
    date = case.get("date") or "—"
    impact = _severity_impact_label(case, person_name=person_name, person_role=person_role)
    ai = case.get("aiAnalysis") or {}
    ai_bit = ""
    if ai.get("summary_ru"):
        ai_bit = f" {_short_text(ai['summary_ru'], max_len=140)}"
    return (
        f"  - **{role}** · «{_short_text(category, max_len=85)}» · "
        f"{_short_text(result, max_len=40)} · {date} · *{impact}*{ai_bit}"
    )


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
    risk_level: str = "",
    courts: dict | None = None,
    taxes: dict | None = None,
    risk_flags: list | None = None,
    lseg: dict | None = None,
    sanctions: dict | None = None,
    director: str | None = None,
    person_name_for_courts: str | None = None,
    max_court_lines: int = 2,
) -> str:
    """Краткое досье одной компании/узла (факты, без LLM)."""
    link = _dossier_case_link(case_id)
    role_part = f" · {role}" if role else ""
    lines = [f"### {name}{role_part} · БИН `{iin_bin}`{link}"]
    if director:
        lines.append(f"- Директор: {_clean_person_display_name(director)}")
    if risk_level:
        lines.append(f"- Уровень риска в системе: {risk_level}")

    lines.extend(_format_lseg_dossier_bullets(lseg, sanctions))

    courts = courts or {}
    cases = [c for c in (courts.get("cases") or []) if isinstance(c, dict)]
    active = courts.get("activeCases", 0) or 0
    if cases or active:
        pname = person_name_for_courts or name
        lines.append(_summarize_courts_for_dossier(cases, pname))
        if max_court_lines > 0:
            top_cases = sorted(
                [c for c in cases if _contract_relevance_tier(c, pname) == "red"],
                key=lambda c: _court_case_importance_score(c, pname),
                reverse=True,
            )[:max_court_lines]
            for case in top_cases:
                lines.append(
                    _format_court_case_dossier_bullet(case, person_name=pname)
                )
    else:
        lines.append("- Суды: не выявлено")

    if taxes:
        status = taxes.get("status") or "—"
        debt = taxes.get("debt", 0) or 0
        lines.append(
            f"- Налоги: {status}, задолженность {debt:,.0f} тг".replace(",", "\u202f")
        )
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
    assessment = enriched.get("assessment") or {}
    info = enrichment.get("companyInfo") or {}
    return _format_company_dossier_card(
        name=str(row.get("company_name") or MISSING),
        iin_bin=str(row.get("iin") or MISSING),
        case_id=row.get("id"),
        role="проверяемый контрагент",
        risk_level=str(
            assessment.get("riskLevel") or row.get("risk_level") or "не определён"
        ),
        courts=enrichment.get("courts"),
        taxes=enrichment.get("taxes"),
        risk_flags=enrichment.get("riskFlags") or [],
        lseg=enriched.get("lseg"),
        sanctions=enrichment.get("sanctions"),
        director=str(info.get("director") or "") or None,
        person_name_for_courts=str(row.get("company_name") or ""),
    )


def _format_company_dossier_from_affiliate(aff: dict) -> str:
    return _format_company_dossier_card(
        name=str(aff.get("name") or MISSING),
        iin_bin=str(aff.get("iinBin") or MISSING),
        case_id=aff.get("case_id"),
        role=str(aff.get("role") or ""),
        risk_level=str(aff.get("riskLevel") or "не определён"),
        courts=aff.get("courts"),
        taxes=aff.get("taxes"),
        risk_flags=aff.get("riskFlags") or [],
        lseg=aff.get("lseg"),
        sanctions=aff.get("sanctions"),
        director=str(aff.get("director") or "") or None,
        person_name_for_courts=str(aff.get("name") or ""),
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


def _build_sanctions_llm_context(row: dict[str, Any]) -> str:
    """Контекст для вывода ИИ по санкциям — без судов и courts-скоринга."""
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    parts: list[str] = [_build_sanctions_facts_block(row)]
    _append_sanctions_snapshot(parts, row)

    score_breakdown = enriched.get("scoreBreakdown")
    if _is_populated(score_breakdown):
        score_lines = []
        for m in score_breakdown:
            metric = str(m.get("metric") or "").lower()
            if metric not in ("sanctions", "pep", "adverse_media"):
                continue
            score_lines.append(
                f"- {m.get('metric', '')}: {m.get('points', m.get('score', 0))} — "
                f"{m.get('reason', m.get('label', ''))}"
            )
        if score_lines:
            parts.append("\n## СКОРИНГ (только санкции/PEP)\n" + "\n".join(score_lines))

    risk_flags = enrichment.get("riskFlags") or []
    san_flags = [f for f in risk_flags if _line_mentions_sanctions(str(f))]
    if san_flags:
        parts.append(
            "\n## ФАКТОРЫ РИСКА Adata (санкции)\n"
            + "\n".join(f"- {f}" for f in san_flags[:10])
        )

    return _truncate_context(
        "\n".join(parts), max_chars=_SECTION_MAX_CHARS["sanctions"]
    )


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
    if "### Краткое сведение" in base:
        return base
    if "### Результаты скрининга" in base and base.count("###") == 1:
        return _append_takeaway_block("sanctions", base)
    if not re.search(r"(^|\n)\s*[-*#]", base):
        return _append_takeaway_block("sanctions", base)
    return _append_takeaway_block("sanctions", base)


async def _generate_sanctions_section_hybrid(
    client: Any,
    row: dict[str, Any],
    company_name: str,
) -> str:
    """LSEG-факты (код) + краткое сведение ИИ (только санкции)."""
    facts = _build_sanctions_facts_block(row)
    context = _build_sanctions_llm_context(row)
    try:
        raw = await _call_llm_section(client, "sanctions", context, company_name)
        conclusion = _normalize_sanctions_output(raw)
        if "### Результаты скрининга" in conclusion:
            return conclusion
        return f"{facts}\n\n{conclusion}"
    except Exception:
        return _normalize_sanctions_output(
            f"{facts}\n\n{_template_section_fallback(row, 'sanctions')}"
        )


def _build_structure_dossiers_block(row: dict[str, Any]) -> str:
    enriched = row.get("enriched_data") or {}
    affiliate_tree = enriched.get("affiliateTree")
    parts = ["### Досье по компаниям\n", _format_company_dossier_from_row(row)]

    for aff in _collect_affiliate_enrichments(affiliate_tree, max_depth=2):
        parts.append(_format_company_dossier_from_affiliate(aff))

    beneficiary = enriched.get("beneficiary")
    if _is_populated(beneficiary) and isinstance(beneficiary, list):
        ben_lines = ["### Бенефициары (справочно)"]
        for b in beneficiary[:8]:
            name_b = b.get("name") or b.get("short_name") or MISSING
            share = b.get("share") or b.get("ownershipShare") or MISSING
            ben_lines.append(f"- {name_b} · доля {share}")
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


def _format_person_courts_for_llm_block(
    person_name: str,
    person_role: str,
    cases: list[dict],
) -> str | None:
    """Только red/yellow дела — контекст для вывода ИИ, не для UI."""
    filtered = [
        c
        for c in cases
        if isinstance(c, dict) and not _should_skip_case_for_report(c)
    ]
    if not filtered:
        return None

    red_cases: list[dict] = []
    yellow_cases: list[dict] = []
    for case in filtered:
        tier = _contract_relevance_tier(case, person_name, person_role=person_role)
        if tier == "red":
            red_cases.append(case)
        elif tier == "yellow":
            yellow_cases.append(case)

    if not red_cases and not yellow_cases:
        return None

    lines = [f"### {person_name}" + (f" · {person_role}" if person_role else "")]
    lines.append(
        f"- Всего записей (без шума): {len(filtered)} · red: {len(red_cases)} · yellow: {len(yellow_cases)}"
    )
    for case in sorted(
        red_cases,
        key=lambda c: _court_case_importance_score(c, person_name, person_role=person_role),
        reverse=True,
    )[:6]:
        role = _extract_case_role_by_parties(case, person_name)
        cat = case.get("category") or case.get("type") or "—"
        lines.append(
            f"  [RED] {role} · «{_short_text(cat, max_len=90)}» · {case.get('date') or '—'}"
        )
        ai = case.get("aiAnalysis") or {}
        if ai.get("summary_ru"):
            lines.append(f"    {_short_text(ai['summary_ru'], max_len=200)}")
    for case in yellow_cases[:4]:
        role = _extract_case_role_by_parties(case, person_name)
        cat = case.get("category") or case.get("type") or "—"
        lines.append(
            f"  [YELLOW] {role} · «{_short_text(cat, max_len=90)}» · {case.get('date') or '—'}"
        )
    return "\n".join(lines)


def _build_courts_llm_context(row: dict[str, Any]) -> str:
    """Контекст для LLM: политика + таблица + только red/yellow дела (без UI-досье)."""
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    company_name = str(row.get("company_name") or "Компания")
    parts: list[str] = [_COURTS_DEAL_POLICY]
    _append_case_officer_snapshot(parts, row)
    parts.append(f"\n## ТАБЛИЦА\n{_format_courts_table_block(row)}")

    subject_blocks: list[str] = []
    company_cases: list[dict] = []
    for case in (enrichment.get("courts") or {}).get("cases") or []:
        if isinstance(case, dict):
            company_cases.append(case)
    detailed = enriched.get("companyCourtCases")
    if isinstance(detailed, list):
        for case in detailed:
            if isinstance(case, dict):
                company_cases.append(case)
    company_block = _format_person_courts_for_llm_block(
        company_name, "компания-контрагент", company_cases
    )
    if company_block:
        subject_blocks.append(company_block)

    meta = enriched.get("individualCourtsMeta") or {}
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
            person_role = str(person_meta.get("role") or "")
            block = _format_person_courts_for_llm_block(
                person_name, person_role, cases
            )
            if block:
                subject_blocks.append(block)

    if subject_blocks:
        parts.append(
            "\n## ДЕЛА ДЛЯ ВЫВОДА (red / yellow)\n" + "\n\n".join(subject_blocks)
        )
    else:
        parts.append("\n## ДЕЛА ДЛЯ ВЫВОДА\nСущественных red/yellow дел не выявлено.")

    return _truncate_context("\n".join(parts), max_chars=_SECTION_MAX_CHARS["courts"])


def _build_structure_conclusion_context(row: dict[str, Any]) -> str:
    parts = [_build_structure_dossiers_block(row)]
    _append_case_officer_snapshot(parts, row)
    enriched = row.get("enriched_data") or {}
    individual_courts = enriched.get("individualCourts")
    meta = enriched.get("individualCourtsMeta")
    ind_text = _format_individual_courts_for_llm(individual_courts, meta)
    if ind_text != MISSING:
        parts.append(f"\n## ПЕРСОНАЛЬНЫЕ СУДЫ (детали)\n{ind_text}")
    return _truncate_context("\n".join(parts), max_chars=_SECTION_MAX_CHARS["structure"])


def _build_courts_conclusion_context(row: dict[str, Any]) -> str:
    return _build_courts_llm_context(row)


def _normalize_llm_conclusion(section: str, text: str) -> str:
    base = _sanitize_llm_text(text or "").strip() or MISSING
    if "### Вывод ИИ" not in base:
        base = f"### Вывод ИИ\n{base}"
    lowered = base.lower()
    if "риск:" not in lowered and "flag" not in lowered:
        risk_tag = _infer_risk_tag(section, base)
        action = _recommended_next_action(section, risk_tag)
        base = f"{base}\n- Риск: {risk_tag}\n- Действие: {action}"
    return base


def _format_courts_conclusion_fallback(row: dict[str, Any]) -> str:
    enriched = row.get("enriched_data") or {}
    individual_courts = enriched.get("individualCourts") or {}
    meta = enriched.get("individualCourtsMeta") or {}
    individual_meta = meta if isinstance(meta, dict) else {}

    lines = ["### Вывод ИИ"]
    has_red = False

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
            person_role = str(person_meta.get("role") or "")
            for case in cases:
                if not isinstance(case, dict):
                    continue
                tier = _contract_relevance_tier(
                    case, person_name, person_role=person_role
                )
                if tier != "red":
                    continue
                has_red = True
                role = _extract_case_role_by_parties(case, person_name)
                cat = case.get("category") or case.get("type") or "—"
                who = "директор" if _is_officer_role(person_role) else person_name
                lines.append(
                    f"- **{who}** ({person_name}): {role} по «{_short_text(cat, 85)}» — "
                    f"**red flag** для сделки (репутация/дисциплина ключевого лица)."
                )

    if not has_red:
        lines.append(
            "- Существенных red flag по судам для блокировки сделки не выявлено "
            "(ДТП/ПДД/мелочь не учитывались)."
        )

    verdict_level = "red" if has_red else "green"
    action = (
        "Эскалировать на юриста/комплаенс: проверить материалы по ст.73 и ключевым лицам."
        if has_red
        else "Суды не блокируют подписание; плановый мониторинг."
    )
    lines.append(f"- Риск: {verdict_level} flag")
    lines.append(f"- Действие: {action}")
    return "\n".join(lines)


def _format_court_case_officer_detail(case: dict, *, person_label: str = "") -> str:
    """One court case with aiAnalysis for LLM context (not truncated like table cells)."""
    ai = case.get("aiAnalysis") or {}
    header = person_label or "—"
    lines = [
        f"### {header}",
        f"- Тип/категория: {case.get('category') or case.get('type') or '—'}",
        f"- Роль: {case.get('role') or '—'}",
        f"- Результат: {case.get('result') or case.get('status') or '—'}",
        f"- Дата: {case.get('date') or '—'}",
    ]
    if ai:
        lines.append(
            f"- AI-разбор: severity={ai.get('severity', '—')}, "
            f"category={ai.get('category', '—')}, outcome={ai.get('outcome', '—')}"
        )
        if ai.get("summary_ru"):
            lines.append(f"  {ai['summary_ru']}")
    defendants = case.get("defendants") or []
    plaintiffs = case.get("plaintiffs") or []
    if defendants:
        lines.append(f"- Ответчики: {', '.join(str(d) for d in defendants[:5])}")
    if plaintiffs:
        lines.append(f"- Истцы: {', '.join(str(p) for p in plaintiffs[:5])}")
    for doc in (case.get("documents") or [])[:3]:
        file_name = doc.get("file_name") or "документ"
        doc_link = doc.get("doc_link") or ""
        if doc_link:
            lines.append(f"  - [{file_name}]({doc_link})")
    return "\n".join(lines)


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


def _append_case_officer_snapshot(parts: list[str], row: dict[str, Any]) -> None:
    """Cross-cutting case facts useful in every LLM section."""
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    assessment = enriched.get("assessment") or {}
    info = enrichment.get("companyInfo") or {}
    director = _clean_person_display_name(info.get("director"))
    parts.append(
        f"\n## СНИМОК КЕЙСА\n"
        f"- Компания: {row.get('company_name') or MISSING}\n"
        f"- БИН: {row.get('iin') or MISSING}\n"
        f"- Директор: {director}\n"
        f"- Уровень риска: {assessment.get('riskLevel') or row.get('risk_level') or MISSING}\n"
        f"- Балл: {enriched.get('totalScore') if enriched.get('totalScore') is not None else MISSING}"
    )
    if assessment.get("summary"):
        parts.append(f"- Оценка (assessment): {assessment['summary']}")
    flags = assessment.get("flags") or []
    if flags:
        parts.append("## ФЛАГИ ОЦЕНКИ")
        for f in flags[:8]:
            parts.append(f"- [{f.get('severity', '')}] {f.get('message', '')}")


def _append_sanctions_snapshot(parts: list[str], row: dict[str, Any]) -> None:
    """Минимальный снимок для санкций — без судов и общего скоринга."""
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    info = enrichment.get("companyInfo") or {}
    director = _clean_person_display_name(info.get("director"))
    parts.append(
        f"\n## КОНТРАГЕНТ\n"
        f"- Компания: {row.get('company_name') or MISSING}\n"
        f"- БИН: {row.get('iin') or MISSING}\n"
        f"- Директор: {director}"
    )
    flags = (enriched.get("assessment") or {}).get("flags") or []
    san_flags = [
        f
        for f in flags
        if _line_mentions_sanctions(str(f.get("message") or ""))
    ]
    if san_flags:
        parts.append("## ФЛАГИ (только санкции/PEP)")
        for f in san_flags[:6]:
            parts.append(f"- [{f.get('severity', '')}] {f.get('message', '')}")


def _format_individual_court_case(case: dict) -> list[str]:
    """Format one individual court case with history and document links."""
    lines = [
        f"- Дело №{case.get('number') or '—'}: {case.get('type') or '—'}, "
        f"суд: {case.get('court') or '—'}, дата: {case.get('date') or '—'}, "
        f"результат: {case.get('result') or '—'}"
    ]
    category = case.get("category")
    if _is_populated(category):
        lines.append(f"  Категория: {category}")
    judge = case.get("judge")
    if _is_populated(judge):
        lines.append(f"  Судья: {judge}")
    defendants = case.get("defendants") or []
    plaintiffs = case.get("plaintiffs") or []
    if defendants:
        lines.append(f"  Ответчики: {', '.join(str(d) for d in defendants[:5])}")
    if plaintiffs:
        lines.append(f"  Истцы: {', '.join(str(p) for p in plaintiffs[:5])}")
    for doc in (case.get("documents") or []):
        file_name = doc.get("file_name") or "документ"
        doc_link = doc.get("doc_link") or ""
        if doc_link:
            lines.append(f"  - [{file_name}]({doc_link})")
        else:
            lines.append(f"  - {file_name}")
    ai = case.get("aiAnalysis") or {}
    if ai.get("summary_ru"):
        lines.append(f"  AI-разбор: {ai['summary_ru']}")
    for event in (case.get("history") or [])[:5]:
        event_date = event.get("event_date") or "—"
        event_name = event.get("name") or "—"
        lines.append(f"  • {event_date}: {event_name}")
        for doc in (event.get("documents") or []):
            file_name = doc.get("file_name") or "документ"
            doc_link = doc.get("doc_link") or ""
            if doc_link:
                lines.append(f"    - [{file_name}]({doc_link})")
            else:
                lines.append(f"    - {file_name}")
    return lines


def _format_individual_courts_for_llm(
    individual_courts: dict[str, Any] | None,
    meta: dict[str, Any] | None,
) -> str:
    """Format individualCourts dict for LLM context with markdown doc links."""
    if not individual_courts or not isinstance(individual_courts, dict):
        return MISSING

    lines: list[str] = []
    meta = meta if isinstance(meta, dict) else {}
    for iin, cases in individual_courts.items():
        if not cases or not isinstance(cases, list):
            continue
        person_meta = meta.get(iin) if isinstance(meta.get(iin), dict) else {}
        name = person_meta.get("name") or iin
        role = person_meta.get("role") or ""
        company_name = person_meta.get("companyName") or ""
        header = f"### {name} (ИИН {iin})"
        if role:
            header += f", {role}"
        if company_name:
            header += f" — {company_name}"
        lines.append(header)
        lines.append(f"Дел: {len(cases)}")
        for case in cases[:8]:
            if isinstance(case, dict):
                lines.extend(_format_individual_court_case(case))
        if len(cases) > 8:
            lines.append(f"  … ещё {len(cases) - 8} дел не показано")

    return "\n".join(lines) if lines else MISSING


def _short_text(value: Any, *, max_len: int = 80) -> str:
    text = str(value or "—").strip()
    if not text:
        return "—"
    text = re.sub(r"\s+", " ", text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _normalize_case_role(raw_role: Any) -> str:
    role = str(raw_role or "").strip().lower()
    if not role:
        return "Не указано"
    if "ответ" in role or "defend" in role:
        return "Ответчик"
    if "ист" in role or "plaint" in role:
        return "Истец"
    if "треть" in role or "third" in role:
        return "Третья сторона"
    return _short_text(raw_role, max_len=28)


def _normalize_person_name_key(raw_name: Any) -> str:
    return re.sub(r"\s+", " ", str(raw_name or "").strip().lower())


def _extract_case_role_by_parties(case: dict[str, Any], person_name: str) -> str:
    name_key = _normalize_person_name_key(person_name)
    defendants = case.get("defendants") or []
    plaintiffs = case.get("plaintiffs") or []
    defendant_keys = {_normalize_person_name_key(x) for x in defendants if x}
    plaintiff_keys = {_normalize_person_name_key(x) for x in plaintiffs if x}
    if name_key and name_key in defendant_keys:
        return "Ответчик"
    if name_key and name_key in plaintiff_keys:
        return "Истец"
    return _normalize_case_role(case.get("role"))


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
    )
    return any(marker in lowered for marker in serious_markers)


def _is_unresolved_case(case: dict[str, Any]) -> bool:
    text = " ".join(
        str(case.get(k) or "")
        for k in ("result", "status")
    ).lower()
    unresolved_markers = ("не заверш", "в производстве", "рассматрива", "pending")
    return any(marker in text for marker in unresolved_markers)


def _collect_court_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    company_name = row.get("company_name") or "Компания"
    rows: list[dict[str, Any]] = []

    company_courts = enrichment.get("courts") or {}
    for case in (company_courts.get("cases") or []):
        if not isinstance(case, dict) or _should_skip_case_for_report(case):
            continue
        category = case.get("category") or case.get("type") or "—"
        tier = _contract_relevance_tier(case, company_name, person_role="компания")
        if tier == "noise":
            continue
        row_item = {
            "person_entity": _short_text(company_name, max_len=46),
            "role_in_case": _normalize_case_role(case.get("role")),
            "category": _short_text(category, max_len=70),
            "result": _short_text(case.get("result") or case.get("status"), max_len=48),
            "date": _short_text(case.get("date"), max_len=24),
            "source_links": _count_case_source_links(case),
            "is_top_officer": False,
            "is_defendant": _normalize_case_role(case.get("role")) == "Ответчик",
            "is_serious": _is_serious_court_category(str(category)),
            "is_unresolved": _is_unresolved_case(case),
            "contract_tier": tier,
        }
        rows.append(row_item)

    company_detailed = enriched.get("companyCourtCases")
    if isinstance(company_detailed, list):
        for case in company_detailed:
            if not isinstance(case, dict) or _should_skip_case_for_report(case):
                continue
            category = case.get("category") or case.get("type") or "—"
            case_role = _normalize_case_role(case.get("role"))
            tier = _contract_relevance_tier(case, company_name, person_role="компания")
            if tier == "noise":
                continue
            rows.append(
                {
                    "person_entity": _short_text(company_name, max_len=46),
                    "role_in_case": case_role,
                    "category": _short_text(category, max_len=70),
                    "result": _short_text(case.get("result") or case.get("status"), max_len=48),
                    "date": _short_text(case.get("date"), max_len=24),
                    "source_links": _count_case_source_links(case),
                    "is_top_officer": False,
                    "is_defendant": case_role == "Ответчик",
                    "is_serious": _is_serious_court_category(str(category)),
                    "is_unresolved": _is_unresolved_case(case),
                    "contract_tier": tier,
                }
            )

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
                case_role = _extract_case_role_by_parties(case, person_name)
                category = case.get("category") or case.get("type") or "—"
                tier = _contract_relevance_tier(
                    case, person_name, person_role=person_role
                )
                if tier == "noise":
                    continue
                row_item = {
                    "person_entity": _short_text(person_name, max_len=46),
                    "role_in_case": case_role,
                    "category": _short_text(category, max_len=70),
                    "result": _short_text(case.get("result") or case.get("status"), max_len=48),
                    "date": _short_text(case.get("date"), max_len=24),
                    "source_links": _count_case_source_links(case),
                    "is_top_officer": is_top_officer,
                    "is_defendant": case_role == "Ответчик",
                    "is_serious": _is_serious_court_category(str(category)),
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


def _build_courts_verdict(rows: list[dict[str, Any]]) -> tuple[str, list[str], str, list[str]]:
    defendants = [r for r in rows if r.get("is_defendant")]
    third_party_only = bool(rows) and all(r.get("role_in_case") == "Третья сторона" for r in rows)
    red_matches = [
        r
        for r in rows
        if r.get("is_top_officer") and r.get("is_defendant") and r.get("is_serious")
    ]

    if red_matches:
        sample = red_matches[0]
        level = "red"
        why = [
            "Выявлен руководитель/директор в роли ответчика по серьёзной категории.",
            f"Категория дела: {sample.get('category')}.",
            "Это прямой индикатор управленческого и репутационного риска для компании.",
        ]
        impact = (
            "Прямая релевантность к компании: поведение ключевого руководителя влияет "
            "на юридические, регуляторные и контрагентские риски."
        )
        actions = [
            "Эскалировать кейс на ручную юридическую проверку до одобрения.",
            "Запросить материалы дела и внутренние объяснения по руководителю.",
        ]
        return level, why, impact, actions

    if third_party_only or not defendants:
        level = "green"
        why = [
            "Прямых ролей ответчика не выявлено.",
            "Участие ограничено третьей стороной или косвенной вовлечённостью.",
        ]
        impact = (
            "Низкая релевантность к риску компании: отсутствуют признаки прямой "
            "судебной ответственности ключевых лиц."
        )
        actions = [
            "Сохранить периодический мониторинг новых дел.",
        ]
        return level, why, impact, actions

    level = "yellow"
    why = [
        "Есть дела с участием ответчиков, но без подтверждённого тяжёлого профиля ключевых руководителей.",
    ]
    if any(r.get("is_unresolved") for r in defendants):
        why.append("Часть дел в статусе рассмотрения/без финального исхода.")
    impact = (
        "Средняя релевантность к компании: риск может повлиять на контрагентский профиль "
        "после уточнения исходов и роли участников."
    )
    actions = [
        "Проверить исход и предмет ключевых дел ответчиков.",
        "Обновить риск-оценку после получения документов.",
    ]
    return level, why[:3], impact, actions[:2]


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
    third_party_count = sum(1 for r in rows_sorted if r.get("role_in_case") == "Третья сторона")
    serious_count = sum(1 for r in rows_sorted if r.get("is_serious"))

    lines = [
        f"Кейс: {company_name}. Судебных записей: {total_cases}.",
        (
            f"Сводка: ответчики {defendant_count}, третья сторона {third_party_count}, "
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
                    _short_text(item.get("role_in_case"), max_len=20).replace("|", "/"),
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


def _format_courts_section(row: dict[str, Any], *, max_rows: int = 8) -> str:
    """Суды без OpenAI: таблица + вывод ИИ."""
    return (
        f"{_format_courts_table_block(row, max_rows=max_rows)}\n\n"
        f"{_format_courts_conclusion_fallback(row)}"
    )


def _build_courts_officer_context(row: dict[str, Any], *, max_cases: int = 25) -> str:
    """Rich LLM context: all cases with aiAnalysis, individual courts, taxes — not table-only."""
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    parts: list[str] = []
    _append_case_officer_snapshot(parts, row)

    taxes = enrichment.get("taxes") or {}
    if _is_populated(taxes):
        debt = taxes.get("debt")
        parts.append(
            f"\n## НАЛОГИ\n"
            f"- Задолженность: {debt if debt is not None else MISSING}\n"
            f"- Статус: {taxes.get('status') or MISSING}"
        )

    parts.append(
        f"\n## ТАБЛИЦА (топ дел, уже будет в отчёте)\n{_format_courts_table_block(row)}"
    )

    company_name = row.get("company_name") or "Компания"
    case_blocks: list[str] = []
    company_courts = enrichment.get("courts") or {}
    for case in (company_courts.get("cases") or [])[:max_cases]:
        if isinstance(case, dict):
            case_blocks.append(_format_court_case_officer_detail(case, person_label=company_name))

    company_detailed = enriched.get("companyCourtCases")
    if isinstance(company_detailed, list):
        for case in company_detailed[:max_cases]:
            if isinstance(case, dict):
                case_blocks.append(
                    _format_court_case_officer_detail(case, person_label=company_name)
                )

    meta = enriched.get("individualCourtsMeta") or {}
    individual_meta = meta if isinstance(meta, dict) else {}
    individual_courts = enriched.get("individualCourts")
    if isinstance(individual_courts, dict):
        for iin, cases in individual_courts.items():
            if not isinstance(cases, list):
                continue
            person_meta = individual_meta.get(iin) if isinstance(individual_meta.get(iin), dict) else {}
            person_name = str(person_meta.get("name") or iin)
            person_role = str(person_meta.get("role") or "")
            label = f"{person_name} (ИИН {iin})"
            if person_role:
                label += f", {person_role}"
            for case in cases[:12]:
                if isinstance(case, dict):
                    case_blocks.append(_format_court_case_officer_detail(case, person_label=label))

    if case_blocks:
        parts.append("\n## ПОЛНЫЙ КОНТЕКСТ ДЕЛ (для анализа)\n" + "\n\n".join(case_blocks[:max_cases]))
    else:
        parts.append(f"\n## ПОЛНЫЙ КОНТЕКСТ ДЕЛ\n{MISSING}")

    return _truncate_context("\n".join(parts), max_chars=_SECTION_MAX_CHARS["courts"])


async def _generate_courts_section_hybrid(
    client: Any,
    row: dict[str, Any],
    company_name: str,
) -> str:
    """Таблица (код) + вывод ИИ (LLM). Без построчного досье в UI."""
    table = _format_courts_table_block(row)
    context = _build_courts_conclusion_context(row)
    try:
        narrative = await _call_llm_section(client, "courts", context, company_name)
        conclusion = _normalize_llm_conclusion("courts", narrative)
        return f"{table}\n\n{conclusion}"
    except Exception:
        return _format_courts_section(row)


async def _generate_structure_section_hybrid(
    client: Any,
    row: dict[str, Any],
    company_name: str,
) -> str:
    """Досье по каждой компании (код) + вывод ИИ (LLM)."""
    dossiers = _build_structure_dossiers_block(row)
    context = _build_structure_conclusion_context(row)
    try:
        narrative = await _call_llm_section(client, "structure", context, company_name)
        conclusion = _normalize_llm_conclusion("structure", narrative)
        return f"{dossiers}\n\n{conclusion}"
    except Exception:
        return _normalize_section_output(
            "structure",
            f"{dossiers}\n\n{_template_section_fallback(row, 'structure')}",
        )


def _build_section_context(
    row: dict[str, Any],
    section: str,
    *,
    section_excerpts: dict[str, str] | None = None,
) -> str:
    """Build minimal LLM context for a single report section."""
    company_name = row.get("company_name") or MISSING
    iin = row.get("iin") or MISSING
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    assessment = enriched.get("assessment") or {}
    max_chars = _SECTION_MAX_CHARS.get(section, 8000)

    if section == "sanctions":
        return _build_sanctions_llm_context(row)

    if section == "courts":
        return _build_courts_officer_context(row)

    if section == "structure":
        parts: list[str] = []
        _append_case_officer_snapshot(parts, row)
        affiliate_tree = enriched.get("affiliateTree")
        if _is_populated(affiliate_tree) and isinstance(affiliate_tree, dict):
            nodes_count = affiliate_tree.get("nodesCount", 0)
            status = affiliate_tree.get("status", MISSING)
            parts.append(f"\n## СТРУКТУРА\nСтатус: {status}. Узлов в дереве: {nodes_count}.")

        affiliate_enrichments = _collect_affiliate_enrichments(affiliate_tree, max_depth=2)
        affiliate_analysis = _format_affiliate_analysis(affiliate_enrichments)
        parts.append(f"\n## АФФИЛИАТЫ (досье по каждому)\n{affiliate_analysis}")

        affiliate_profiles = enriched.get("affiliateProfiles") or {}
        if affiliate_profiles:
            prof_lines = ["\n## ПРОФИЛИ АФФИЛИАТОВ L1"]
            for bin_val, prof in affiliate_profiles.items():
                if not isinstance(prof, dict):
                    continue
                courts = prof.get("courts") or {}
                taxes = prof.get("taxes") or {}
                flags = prof.get("riskFlags") or []
                line = (
                    f"- БИН {bin_val}: директор={prof.get('director', '—')}, "
                    f"суды={courts.get('activeCases', 0)} активных, "
                    f"налоги={taxes.get('status', '?')}"
                )
                if flags:
                    line += f", флаги: {'; '.join(str(f) for f in flags[:2])}"
                prof_lines.append(line)
            parts.append("\n".join(prof_lines))

        beneficiary = enriched.get("beneficiary")
        if _is_populated(beneficiary) and isinstance(beneficiary, list):
            ben_lines = [f"Записей UBO: {len(beneficiary)}"]
            for b in beneficiary[:10]:
                name_b = b.get("name") or b.get("short_name") or MISSING
                share = b.get("share") or b.get("ownershipShare") or MISSING
                ben_lines.append(f"- {name_b} | доля: {share}")
            parts.append("\n## БЕНЕФИЦИАРЫ\n" + "\n".join(ben_lines))

        relation_extended = enriched.get("relationExtended")
        if _is_populated(relation_extended) and isinstance(relation_extended, dict):
            by_head = (
                relation_extended.get("affiliation_by_head")
                or relation_extended.get("affiliationByHead")
                or []
            )
            by_founder = (
                relation_extended.get("affiliation_by_founder")
                or relation_extended.get("affiliationByFounder")
                or []
            )
            head_list = by_head if isinstance(by_head, list) else []
            founder_list = by_founder if isinstance(by_founder, list) else []
            if head_list or founder_list:
                rel_lines = [f"По руководителю: {len(head_list)}"]
                for a in head_list[:6]:
                    rel_lines.append(
                        f"- {a.get('name', MISSING)} | "
                        f"{a.get('iin_bin') or a.get('iinBin', MISSING)}"
                    )
                rel_lines.append(f"По учредителям: {len(founder_list)}")
                for a in founder_list[:6]:
                    rel_lines.append(
                        f"- {a.get('name', MISSING)} | "
                        f"{a.get('iin_bin') or a.get('iinBin', MISSING)}"
                    )
                parts.append("\n## СВЯЗИ ЧЕРЕЗ ДИРЕКТОРА/УЧРЕДИТЕЛЕЙ\n" + "\n".join(rel_lines))

        trustworthy_plus = enriched.get("trustworthyPlus")
        if _is_populated(trustworthy_plus) and isinstance(trustworthy_plus, dict):
            tp_text = _format_trustworthy_plus_summary(trustworthy_plus)
            if tp_text:
                parts.append(f"\n## TRUSTWORTHY-PLUS\n{tp_text}")

        nr_data = (enriched.get("nonResidents") or {}).get("data") if isinstance(
            enriched.get("nonResidents"), dict
        ) else []
        if _is_populated(nr_data):
            nr_lines = [f"Нерезидентов: {len(nr_data)}"]
            for nr in nr_data[:12]:
                name_nr = nr.get("name") or nr.get("short_name") or MISSING
                country = nr.get("country") or nr.get("countryCode") or MISSING
                nr_lines.append(f"- {name_nr} | {country}")
            parts.append("\n## НЕРЕЗИДЕНТЫ\n" + "\n".join(nr_lines))

        director_profile = enriched.get("directorProfile")
        if _is_populated(director_profile) and isinstance(director_profile, dict):
            dir_courts = director_profile.get("courts") or {}
            dir_flags = director_profile.get("riskFlags") or []
            parts.append(
                f"\n## ПРОФИЛЬ ДИРЕКТОРА\n"
                f"- Суды (активных): {dir_courts.get('activeCases', 0)}\n"
                f"- Флаги: {'; '.join(str(f) for f in dir_flags[:5]) or 'нет'}"
            )

        individual_courts = enriched.get("individualCourts")
        meta = enriched.get("individualCourtsMeta")
        ind_text = _format_individual_courts_for_llm(individual_courts, meta)
        if ind_text != MISSING:
            parts.append(f"\n## ПЕРСОНАЛЬНЫЕ СУДЫ\n{ind_text}")

        return _truncate_context("\n".join(parts), max_chars=max_chars)

    if section == "summary":
        parts = [
            f"# {company_name} (БИН {iin})",
            f"Уровень риска: {assessment.get('riskLevel') or row.get('risk_level') or MISSING}",
            f"Итоговый балл: {enriched.get('totalScore') if enriched.get('totalScore') is not None else MISSING}",
        ]
        if section_excerpts:
            for key, title in (
                ("sanctions", "Санкционный анализ"),
                ("courts", "Судебные дела"),
                ("structure", "Структура и аффилиаты"),
            ):
                excerpt = (section_excerpts.get(key) or "")[:_SUMMARY_SECTION_EXCERPT_CHARS]
                parts.append(f"\n## {title}\n{excerpt or MISSING}")
        score_breakdown = enriched.get("scoreBreakdown")
        if _is_populated(score_breakdown):
            score_lines = []
            for m in score_breakdown[:7]:
                score_lines.append(
                    f"- {m.get('metric', '')}: {m.get('points', m.get('score', 0))} — "
                    f"{m.get('reason', m.get('label', ''))}"
                )
            parts.append("\n## СКОРИНГ\n" + "\n".join(score_lines))
        return _truncate_context("\n".join(parts), max_chars=max_chars)

    return MISSING


def _template_section_fallback(row: dict[str, Any], section: str) -> str:
    """Template fallback for a single section when LLM call fails."""
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    assessment = enriched.get("assessment") or {}
    company_name = row.get("company_name") or MISSING

    if section == "sanctions":
        return _build_sanctions_facts_block(row)

    if section == "courts":
        return _format_courts_section(row)

    if section == "structure":
        return _build_structure_dossiers_block(row)

    if section == "summary":
        risk = assessment.get("riskLevel") or row.get("risk_level") or MISSING
        summary = assessment.get("summary") or MISSING
        score = enriched.get("totalScore")
        score_part = f" Балл: {score}." if score is not None else ""
        return f"{summary}{score_part} Уровень риска: {risk}."

    return MISSING


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
        if line.startswith("### Краткое сведение") or line.startswith("### Вывод ИИ"):
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


def _infer_risk_tag(section: str, text: str) -> str:
    lowered = text.lower()
    if section == "courts":
        if any(
            m in lowered
            for m in (
                "red flag",
                "ст. 73",
                "ст.73",
                "статья 73",
                "семейно-бытов",
                "эскалац",
            )
        ):
            return "red flag"
        if any(m in lowered for m in ("yellow", "доп. провер", "налог", "договор")):
            return "yellow flag"
        return "green flag"
    red_markers = (
        "санкц",
        "pep",
        "уголов",
        "высок",
        "критич",
        "задолж",
        "red flag",
    )
    yellow_markers = ("средн", "провер", "совпад", "иск", "налог")
    if any(marker in lowered for marker in red_markers):
        return "red flag"
    if any(marker in lowered for marker in yellow_markers):
        return "yellow flag"
    if section == "sanctions" and "чист" in lowered:
        return "green flag"
    return "green flag"


def _recommended_next_action(section: str, risk_tag: str) -> str:
    if section == "sanctions":
        if risk_tag == "red flag":
            return "Запросить расширенную KYC/санкционную проверку и эскалировать комплаенс-офицеру."
        if risk_tag == "yellow flag":
            return "Провести ручную верификацию совпадений и обновить скрининг по уточнённым данным."
        return "Зафиксировать результат и повторить санкционный скрининг перед сделкой."
    if section == "courts":
        if risk_tag == "red flag":
            return "Проверить материалы дел и приостановить согласование до юридического заключения."
        if risk_tag == "yellow flag":
            return "Запросить детали по ключевым делам и оценить финансовое влияние."
        return "Сохранить мониторинг судебной активности на период сделки."
    if risk_tag == "red flag":
        return "Запросить подтверждающие документы по структуре и цепочке владения."
    if risk_tag == "yellow flag":
        return "Уточнить непрозрачные связи и обновить карту аффилиатов."
    return "Принять структуру к сведению и выполнить плановый повторный скрининг."


def _append_takeaway_block(section: str, text: str) -> str:
    normalized = text.strip()
    if "### Краткое сведение" in normalized:
        return normalized
    findings = _extract_key_findings(normalized, max_items=2)
    if not findings:
        findings = ["Данные раздела ограничены или отсутствуют."]
    risk_tag = _infer_risk_tag(section, normalized)
    action = _recommended_next_action(section, risk_tag)
    block_lines = ["### Краткое сведение"]
    for item in findings[:2]:
        block_lines.append(f"- Ключевой вывод: {item}")
    block_lines.append(f"- Риск: {risk_tag}")
    block_lines.append(f"- Следующее действие: {action}")
    return f"{normalized}\n\n" + "\n".join(block_lines)


def _normalize_section_output(section: str, text: str) -> str:
    if section == "sanctions":
        return _normalize_sanctions_output(text)
    base = _sanitize_llm_text(text or "").strip() or MISSING
    if section in ("courts", "structure"):
        if "### Досье" in base or "### Вывод ИИ" in base:
            return base
        if section == "courts":
            return _normalize_llm_conclusion("courts", base)
        return _normalize_llm_conclusion("structure", base)
    if section == "courts":
        return _normalize_llm_conclusion("courts", base)
    readable = _make_readable_markdown(base)
    return _append_takeaway_block(section, readable)


_RISK_LEVEL_RU = {
    "low": "низкий",
    "medium": "средний",
    "high": "высокий",
    "critical": "критический",
}

_METRIC_LABEL_RU = {
    "sanctions": "Санкции",
    "courts": "Суды",
    "taxes": "Налоги",
    "pep": "PEP",
    "adverse_media": "Негативные СМИ",
    "legal_status": "Правовой статус",
    "affiliate_risk": "Аффилиаты",
}


def _build_summary_facts_header(row: dict[str, Any]) -> str:
    """Читаемая шапка резюме — каждый факт с новой строки."""
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    assessment = enriched.get("assessment") or {}
    info = enrichment.get("companyInfo") or {}

    risk_raw = (assessment.get("riskLevel") or row.get("risk_level") or "").lower()
    risk_ru = _RISK_LEVEL_RU.get(risk_raw, risk_raw) or MISSING
    score = enriched.get("totalScore")
    director = _clean_person_display_name(info.get("director"))

    lseg = enriched.get("lseg") or {}
    san = lseg.get("sanctions") or {}
    pep = lseg.get("pep") or {}

    if san.get("isOnList"):
        lseg_san = "🔴 под санкциями WC1"
    else:
        hits = san.get("hits") or []
        lseg_san = f"⚠️ совпадения в WC1 ({len(hits)})" if hits else "✅ санкций нет"

    lseg_pep = "🔴 PEP выявлен" if pep.get("isHit") else "✅ PEP не выявлен"

    score_str = f"{score}" if score is not None else MISSING
    lines = [
        f"| | |",
        f"|---|---|",
        f"| **Компания** | {row.get('company_name') or MISSING} |",
        f"| **БИН** | {row.get('iin') or MISSING} |",
        f"| **Директор** | {director} |",
        f"| **Уровень риска** | {risk_ru} |",
        f"| **Итоговый балл** | {score_str} |",
        f"| **LSEG санкции** | {lseg_san} |",
        f"| **LSEG PEP** | {lseg_pep} |",
    ]

    breakdown = enriched.get("scoreBreakdown") or []
    nonzero = [
        m for m in breakdown
        if (m.get("points") or m.get("score") or 0) != 0
    ]
    if nonzero:
        lines.append("")
        lines.append("**Метрики риска:**")
        for m in nonzero[:7]:
            pts = m.get("points", m.get("score", 0))
            metric_key = str(m.get("metric") or "").lower()
            label = _METRIC_LABEL_RU.get(metric_key, m.get("metric", ""))
            reason = m.get("reason") or m.get("label") or ""
            lines.append(f"- **{label}** ({pts} балл{'а' if 1 < abs(pts) < 5 else ''}) — {reason}")

    return "\n".join(lines)


def _combine_sectional_report(
    company_name: str,
    summary: str,
    sections: dict[str, str],
    sources_hint: str,
    row: dict[str, Any] | None = None,
) -> str:
    sanctions = _normalize_section_output("sanctions", sections.get("sanctions", MISSING))
    courts = _normalize_section_output("courts", sections.get("courts", MISSING))
    structure = _normalize_section_output("structure", sections.get("structure", MISSING))
    summary_block = summary.strip()
    if row is not None:
        facts_header = _build_summary_facts_header(row)
        summary_block = f"{facts_header}\n\n{summary_block}"
    return (
        f"# Отчёт\n\n"
        f"## Резюме\n{summary_block}\n\n"
        f"## 1. Санкционный анализ\n{sanctions}\n\n"
        f"## 2. Судебные дела\n{courts}\n\n"
        f"## 3. Структура\n{structure}\n"
    )


async def _call_llm_section(
    client: Any,
    section: str,
    context: str,
    company_name: str,
) -> str:
    system_prompt = _SECTION_PROMPTS[section]
    user_prompts = {
        "sanctions": (
            f"По фактам LSEG для «{company_name}» напиши ТОЛЬКО ### Краткое сведение. "
            f"Без судов, без налогов, без структуры."
        ),
        "courts": (
            f"По таблице и red/yellow делам для «{company_name}» напиши только "
            f"### Вывод ИИ. Ст.73 семейно-бытовое у директора-ответчика = red flag. "
            f"ДТП/ПДД не блокируют сделку — не выноси в red."
        ),
        "structure": (
            f"По досье компаний для «{company_name}» напиши только блок "
            f"### Вывод ИИ (связи, рисковые аффилиаты, что проверить)."
        ),
        "summary": f"Составь executive summary для «{company_name}».",
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
        max_tokens=3000 if section == "summary" else 2800,
    )
    content = response.choices[0].message.content or ""
    if section == "summary":
        return _sanitize_llm_text(content)
    if section == "sanctions":
        return _normalize_sanctions_output(content)
    if section in ("courts", "structure"):
        return _normalize_llm_conclusion(section, content)
    return _normalize_section_output(section, content)


def _format_affiliate_analysis(affiliates: list[dict]) -> str:
    if not affiliates:
        return "Данные по аффилиатам отсутствуют или не загружены."
    return "\n\n".join(_format_company_dossier_from_affiliate(aff) for aff in affiliates)


def _build_full_context(row: dict[str, Any]) -> str:
    """Build compact but complete context for LLM from all case data."""
    company_name = row.get("company_name") or MISSING
    iin = row.get("iin") or MISSING
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    assessment = enriched.get("assessment") or {}
    trustworthy_plus = enriched.get("trustworthyPlus")
    beneficiary = enriched.get("beneficiary")
    non_residents = enriched.get("nonResidents")
    relation_extended = enriched.get("relationExtended")
    affiliate_tree = enriched.get("affiliateTree")
    score_breakdown = enriched.get("scoreBreakdown")
    total_score = enriched.get("totalScore")

    parts: list[str] = [
        f"# ДОСЬЕ КОНТРАГЕНТА: {company_name}",
        f"БИН/ИИН: {iin}",
    ]

    risk = assessment.get("riskLevel") or row.get("risk_level")
    parts.append(f"Уровень риска: {risk if _is_populated(risk) else MISSING}")
    parts.append(
        f"Итоговый балл: {total_score if total_score is not None else MISSING}"
    )

    sources_used = _list_data_sources(enriched)
    sources_block = (
        "\n".join(f"- {s}" for s in sources_used)
        if sources_used
        else MISSING
    )
    parts.append(f"\n## ИСТОЧНИКИ ДАННЫХ (фактически доступные)\n{sources_block}")
    _log_section("ИСТОЧНИКИ ДАННЫХ", sources_block)

    if _is_populated(enrichment):
        info = enrichment.get("companyInfo") or {}
        profile_lines = [
            f"Директор: {info.get('director') if _is_populated(info.get('director')) else MISSING}",
            f"Статус: {info.get('operatingStatus') if _is_populated(info.get('operatingStatus')) else MISSING}",
            f"Дата регистрации: {info.get('registrationDate') if _is_populated(info.get('registrationDate')) else MISSING}",
            f"Отрасль: {info.get('industry') if _is_populated(info.get('industry')) else MISSING}",
            f"Адрес: {info.get('address') if _is_populated(info.get('address')) else MISSING}",
        ]
        employees = info.get("employees")
        if employees is not None and employees != 0:
            profile_lines.append(f"Сотрудников: {employees}")
        profile_text = "\n".join(profile_lines)
        parts.append(f"\n## ПРОФИЛЬ КОМПАНИИ\n{profile_text}")
        _log_section("ПРОФИЛЬ КОМПАНИИ", profile_text)

        taxes = enrichment.get("taxes") or {}
        if _is_populated(taxes):
            tax_lines = []
            debt = taxes.get("debt")
            if debt is not None:
                tax_lines.append(f"Задолженность: {debt:,.0f} тг".replace(",", " "))
            status = taxes.get("status")
            if _is_populated(status):
                tax_lines.append(f"Статус: {status}")
            yearly = taxes.get("yearlyPayments") or []
            for row_y in yearly[:3]:
                tax_lines.append(
                    f"  {row_y.get('year')}: {row_y.get('amount', 0):,.0f} тг".replace(
                        ",", " "
                    )
                )
            tax_text = "\n".join(tax_lines) if tax_lines else MISSING
            parts.append(f"\n## НАЛОГОВЫЕ ДАННЫЕ\n{tax_text}")
            _log_section("НАЛОГОВЫЕ ДАННЫЕ", tax_text)

        courts = enrichment.get("courts") or {}
        court_cases = courts.get("cases") or []
        if _is_populated(courts) or court_cases:
            court_lines = [
                f"Активные: {courts.get('activeCases', 0)}",
                f"Завершённые: {courts.get('completedCases', 0)}",
            ]
            for c in court_cases[:3]:
                court_lines.append(_format_court_case_line(c))
            court_text = "\n".join(court_lines)
            parts.append(f"\n## СУДЕБНЫЕ ДЕЛА\n{court_text}")
            _log_section("СУДЕБНЫЕ ДЕЛА", court_text)
        else:
            parts.append(f"\n## СУДЕБНЫЕ ДЕЛА\n{MISSING}")
            _log_section("СУДЕБНЫЕ ДЕЛА", MISSING)

        risk_flags = enrichment.get("riskFlags") or []
        if risk_flags:
            flags_text = "\n".join(f"- {f}" for f in risk_flags)
            parts.append(f"\n## ФАКТОРЫ РИСКА (Adata)\n{flags_text}")
            _log_section("ФАКТОРЫ РИСКА", flags_text)
    else:
        parts.append(f"\n## ПРОФИЛЬ КОМПАНИИ\n{MISSING}")
        _log_section("ПРОФИЛЬ КОМПАНИИ", MISSING)

    if _is_populated(score_breakdown):
        score_lines = []
        for m in score_breakdown:
            score_lines.append(
                f"- {m.get('metric', '')}: {m.get('points', m.get('score', 0))} — "
                f"{m.get('reason', m.get('label', ''))}"
            )
        score_text = "\n".join(score_lines)
        parts.append(f"\n## СКОРИНГ (7 метрик)\n{score_text}")
        _log_section("СКОРИНГ", score_text)

    audit_ctx = dict(enriched)
    audit_ctx["_company_name"] = company_name
    audit_text = _format_lseg_screening_summary(audit_ctx)
    parts.append(f"\n## LSEG ПРОВЕРКА (компания, директор, аффилиаты)\n{audit_text}")
    _log_section("LSEG ПРОВЕРКА", audit_text)

    affiliate_enrichments = _collect_affiliate_enrichments(affiliate_tree, max_depth=2)
    affiliate_analysis = _format_affiliate_analysis(affiliate_enrichments)
    parts.append(
        f"\n## АНАЛИЗ АФФИЛИАТОВ (РЕКУРСИВНЫЙ, ГЛУБИНА 2)\n{affiliate_analysis}"
    )
    _log_section(
        "АНАЛИЗ АФФИЛИАТОВ",
        f"{len(affiliate_enrichments)} аффилиатов с данными",
    )
    logger.info(
        "full_report affiliate enrichments: %d nodes loaded",
        len(affiliate_enrichments),
    )

    if _is_populated(trustworthy_plus) and isinstance(trustworthy_plus, dict):
        tp_text = _format_trustworthy_plus_summary(trustworthy_plus)
        if tp_text:
            parts.append(f"\n## TRUSTWORTHY-PLUS\n{tp_text}")
            _log_section("TRUSTWORTHY-PLUS", tp_text)

    if _is_populated(beneficiary) and isinstance(beneficiary, list):
        ben_lines = [f"Записей: {len(beneficiary)}"]
        for b in beneficiary[:10]:
            name_b = b.get("name") or b.get("short_name") or MISSING
            share = b.get("share") or b.get("ownershipShare") or b.get("ownership") or MISSING
            level = b.get("level") or b.get("chainLevel") or MISSING
            ben_lines.append(f"- {name_b} | доля: {share} | уровень: {level}")
        ben_text = "\n".join(ben_lines)
        parts.append(f"\n## БЕНЕФИЦИАРНАЯ СТРУКТУРА (UBO)\n{ben_text}")
        _log_section("БЕНЕФИЦИАРНАЯ СТРУКТУРА", ben_text)

    nr_data = (non_residents if isinstance(non_residents, dict) else {}).get("data") or []
    if _is_populated(nr_data):
        nr_lines = [f"Записей: {len(nr_data)}"]
        for nr in nr_data[:10]:
            name_nr = nr.get("name") or nr.get("short_name") or MISSING
            country = nr.get("country") or nr.get("countryCode") or MISSING
            nr_lines.append(f"- {name_nr} | страна: {country}")
        nr_text = "\n".join(nr_lines)
        parts.append(f"\n## НЕРЕЗИДЕНТЫ\n{nr_text}")
        _log_section("НЕРЕЗИДЕНТЫ", nr_text)

    if _is_populated(relation_extended) and isinstance(relation_extended, dict):
        by_head = (
            relation_extended.get("affiliation_by_head")
            or relation_extended.get("affiliationByHead")
            or []
        )
        by_founder = (
            relation_extended.get("affiliation_by_founder")
            or relation_extended.get("affiliationByFounder")
            or []
        )
        head_list = by_head if isinstance(by_head, list) else []
        founder_list = by_founder if isinstance(by_founder, list) else []
        if head_list or founder_list:
            rel_lines = [f"По руководителю: {len(head_list)}"]
            for a in head_list[:8]:
                rel_lines.append(
                    f"- {a.get('name', MISSING)} | {a.get('iin_bin') or a.get('iinBin', MISSING)}"
                )
            rel_lines.append(f"По учредителям: {len(founder_list)}")
            for a in founder_list[:8]:
                rel_lines.append(
                    f"- {a.get('name', MISSING)} | {a.get('iin_bin') or a.get('iinBin', MISSING)}"
                )
            rel_text = "\n".join(rel_lines)
            parts.append(f"\n## АФФИЛИАТЫ ЧЕРЕЗ ДИРЕКТОРА/УЧРЕДИТЕЛЕЙ\n{rel_text}")
            _log_section("АФФИЛИАТЫ ЧЕРЕЗ ДИРЕКТОРА", rel_text)

    if _is_populated(affiliate_tree) and isinstance(affiliate_tree, dict):
        tree = affiliate_tree
        tree_lines = [
            f"Статус: {tree.get('status', MISSING)}",
            f"Узлов: {tree.get('nodesCount', 0)}",
            _format_affiliate_tree_compact(tree),
        ]
        tree_text = "\n".join(tree_lines)
        parts.append(f"\n## ДЕРЕВО АФФИЛИАТОВ\n{tree_text}")
        _log_section("ДЕРЕВО АФФИЛИАТОВ", tree_text)

    director_profile = enriched.get("directorProfile")
    if _is_populated(director_profile) and isinstance(director_profile, dict):
        dir_courts = director_profile.get("courts") or {}
        dir_companies = director_profile.get("affiliates") or {}
        dir_flags = director_profile.get("riskFlags") or []
        director_text = (
            f"Другие компании директора: {_format_director_companies(dir_companies)}\n"
            f"Судебные дела директора как физлица: активных {dir_courts.get('activeCases', 0)}, "
            f"сумма {dir_courts.get('totalAmount', 0)} тг\n"
            f"Риск-флаги: {'; '.join(str(f) for f in dir_flags) or 'нет'}"
        )
        parts.append(f"\n## ПРОФИЛЬ ДИРЕКТОРА (по ИИН через Adata)\n{director_text}")
        _log_section("ПРОФИЛЬ ДИРЕКТОРА", director_text)

    individual_profiles = enriched.get("individualProfiles") or {}
    if individual_profiles:
        ip_lines = []
        for p_iin, prof in individual_profiles.items():
            if not isinstance(prof, dict):
                continue
            basic = prof.get("basicFl") or {}
            reliability = prof.get("reliabilityFl") or {}
            name = basic.get("name") or f"ИИН {p_iin}"
            age = basic.get("age")
            alive = basic.get("alive")
            pep = basic.get("is_public_official")
            flags: list[str] = []
            if reliability.get("terrorist"):
                flags.append("ТЕРРОРИСТ")
            if reliability.get("terrorism_involved"):
                flags.append("причастен к терроризму")
            if reliability.get("pedophile"):
                flags.append("реестр педофилов")
            if reliability.get("missing"):
                flags.append("пропавший без вести")
            if reliability.get("citizen_hiding_from_investigation"):
                flags.append("скрывается от следствия")
            if reliability.get("enforcement_debt"):
                flags.append("долг по исп. производству")
            if reliability.get("ban_leaving"):
                flags.append(f"запрет на выезд (сумма: {reliability.get('ban_leaving_sum', 0)})")
            if reliability.get("alimony_payer"):
                flags.append("алиментщик")
            tax_debt = reliability.get("tax_debt") or 0
            if isinstance(tax_debt, (int, float)) and tax_debt > 0:
                flags.append(f"налоговый долг: {tax_debt:,.0f} тг".replace(",", " "))

            line = f"- {name} (ИИН {p_iin})"
            if age:
                line += f", {age} лет"
            if alive is False:
                line += ", УМЕР"
            if pep:
                line += ", ПДЛ (публичное должностное лицо)"
            if flags:
                line += f" | Флаги: {'; '.join(flags)}"
            else:
                line += " | Флаги: нет"

            court = prof.get("courtCaseFl") or {}
            civil = int(court.get("total_civil_count") or 0)
            criminal = int(court.get("total_criminal_count") or 0)
            admin = int(court.get("total_administrative_count") or 0)
            if civil + criminal + admin > 0:
                line += f" | Суды: Г:{civil} У:{criminal} А:{admin}"

            ip_lines.append(line)

        if ip_lines:
            ip_text = "\n".join(ip_lines)
            parts.append(f"\n## ПРОФИЛИ ФИЗЛИЦ (директор + учредители, Adata individual/info)\n{ip_text}")
            _log_section("ПРОФИЛИ ФИЗЛИЦ", ip_text)

    affiliate_profiles = enriched.get("affiliateProfiles") or {}
    if affiliate_profiles:
        profile_lines = ["\n## ДАННЫЕ ПО АФФИЛИАТАМ (Adata)"]
        for bin_val, prof in affiliate_profiles.items():
            if not isinstance(prof, dict):
                continue
            courts = prof.get("courts") or {}
            taxes = prof.get("taxes") or {}
            flags = prof.get("riskFlags") or []
            line = (
                f"- БИН {bin_val}: директор={prof.get('director', '—')}, "
                f"суды={courts.get('activeCases', 0)} активных, "
                f"налоги={taxes.get('status', '?')} долг={taxes.get('debt', 0)} тг"
            )
            if flags:
                line += f", флаги: {'; '.join(str(f) for f in flags[:2])}"
            profile_lines.append(line)
        profiles_text = "\n".join(profile_lines)
        parts.append(profiles_text)
        _log_section("ДАННЫЕ ПО АФФИЛИАТАМ", profiles_text)

    flags = assessment.get("flags") or []
    if flags:
        flag_text = "\n".join(
            f"- [{f.get('severity', '')}] {f.get('message', '')}" for f in flags[:5]
        )
        parts.append(f"\n## ФЛАГИ ОЦЕНКИ\n{flag_text}")
        _log_section("ФЛАГИ ОЦЕНКИ", flag_text)

    context = "\n".join(parts)
    return _truncate_context(context, max_chars=60000)


def _template_full_report(row: dict[str, Any]) -> str:
    """Generate a structured text report without LLM based on case data only."""
    company_name = row.get("company_name") or MISSING
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment") or {}
    assessment = enriched.get("assessment") or {}
    lseg = enriched.get("lseg")
    beneficiary = enriched.get("beneficiary") or []
    non_residents_data = (enriched.get("nonResidents") or {}).get("data") or []
    relation_extended = enriched.get("relationExtended") or {}
    lseg_extended = enriched.get("lsegExtended") or {}
    total_score = enriched.get("totalScore")
    sources_used = _list_data_sources(enriched)

    risk_level = assessment.get("riskLevel") or row.get("risk_level")
    risk_labels = {
        "low": "НИЗКИЙ",
        "medium": "СРЕДНИЙ",
        "high": "ВЫСОКИЙ",
        "critical": "КРИТИЧЕСКИЙ",
    }
    risk_label = risk_labels.get(str(risk_level), str(risk_level or MISSING).upper())

    info = enrichment.get("companyInfo") or {}
    taxes = enrichment.get("taxes") or {}
    courts = enrichment.get("courts") or {}

    company_hits = (lseg.get("sanctions") or {}).get("hits") or [] if lseg else []
    director_hits = (lseg.get("pep") or {}).get("individuals") or [] if lseg else []
    ext_sanctioned = sum(
        1
        for v in (lseg_extended or {}).values()
        if isinstance(v, dict) and v.get("isOnSanctionList")
    )
    total_lseg_hits = len(company_hits) + len(director_hits) + ext_sanctioned

    flags = assessment.get("flags") or []
    flags_text = (
        "\n".join(f"- {f.get('message', '')}" for f in flags[:8])
        if flags
        else MISSING
    )

    ubo_lines = []
    for b in beneficiary[:10]:
        name = b.get("name") or b.get("short_name")
        if not _is_populated(name):
            continue
        share = b.get("share") or b.get("ownershipShare") or MISSING
        level = b.get("level") or b.get("chainLevel") or MISSING
        ubo_lines.append(f"- {name} | доля: {share} | уровень: {level}")
    ubo_text = "\n".join(ubo_lines) if ubo_lines else MISSING

    nr_lines = []
    for nr in non_residents_data[:10]:
        name = nr.get("name") or nr.get("short_name")
        if not _is_populated(name):
            continue
        country = nr.get("country") or nr.get("countryCode") or MISSING
        nr_lines.append(f"- {name} | {country}")
    nr_text = "\n".join(nr_lines) if nr_lines else MISSING

    lseg_ext_text = (
        _format_lseg_extended_block(lseg_extended) if lseg_extended else MISSING
    )

    audit_narrative = (
        _format_lseg_screening_summary({**enriched, "_company_name": company_name})
        if lseg
        else MISSING
    )

    by_head = (
        relation_extended.get("affiliation_by_head")
        or relation_extended.get("affiliationByHead")
        or []
    )
    by_founder = (
        relation_extended.get("affiliation_by_founder")
        or relation_extended.get("affiliationByFounder")
        or []
    )
    rel_parts: list[str] = []
    for a in (by_head if isinstance(by_head, list) else [])[:8]:
        if _is_populated(a.get("name")):
            rel_parts.append(f"- [директор] {a.get('name')}")
    for a in (by_founder if isinstance(by_founder, list) else [])[:8]:
        if _is_populated(a.get("name")):
            rel_parts.append(f"- [учредитель] {a.get('name')}")
    rel_text = "\n".join(rel_parts) if rel_parts else MISSING

    affiliate_tree = enriched.get("affiliateTree")
    affiliate_enrichments = _collect_affiliate_enrichments(affiliate_tree, max_depth=2)
    affiliate_analysis = _format_affiliate_analysis(affiliate_enrichments)

    sanction_details = []
    for h in company_hits[:5]:
        sanction_details.append(
            f"  * {h.get('primaryName', '')} ({h.get('matchStrength', '')}, score {h.get('matchScore', 0)})"
            f" — {', '.join(h.get('sanctionLists') or [])}"
            f" — {', '.join(h.get('countryNames') or [])}"
        )
    sanction_text = "\n".join(sanction_details) if sanction_details else MISSING

    tax_debt = taxes.get("debt") if taxes.get("debt") is not None else None
    summary = assessment.get("summary") or MISSING

    director_line = (
        f"Директор: {info.get('director')}."
        if _is_populated(info.get("director"))
        else MISSING
    )
    status_line = (
        f"Статус: {info.get('operatingStatus')}."
        if _is_populated(info.get("operatingStatus"))
        else ""
    )

    recommendation = "ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА"
    rec_reason = MISSING
    if risk_level == "low" and total_lseg_hits == 0 and lseg:
        recommendation = "ОДОБРИТЬ"
        rec_reason = "Низкий уровень риска, отсутствие санкционных совпадений (по данным LSEG)."
    elif risk_level in ("high", "critical") or total_lseg_hits > 0:
        recommendation = "ОТКАЗАТЬ"
        parts_reason = []
        if risk_level:
            parts_reason.append(f"уровень риска {risk_label}")
        if ext_sanctioned:
            parts_reason.append(f"санкционные аффилиаты/учредители ({ext_sanctioned})")
        if company_hits or (lseg and (lseg.get("sanctions") or {}).get("isOnList")):
            parts_reason.append("совпадения LSEG по компании")
        rec_reason = "Выявлено: " + "; ".join(parts_reason) + "." if parts_reason else MISSING

    sources_section = (
        "\n".join(f"- {s}" for s in sources_used) if sources_used else MISSING
    )

    tax_section = MISSING
    if tax_debt is not None or _is_populated(taxes.get("status")):
        debt_str = f"{tax_debt:,.0f} тг".replace(",", " ") if tax_debt is not None else MISSING
        tax_section = (
            f"- Налоговая задолженность: {debt_str} "
            f"(статус: {taxes.get('status') if _is_populated(taxes.get('status')) else MISSING})"
        )

    courts_section = MISSING
    if _is_populated(courts):
        courts_section = (
            f"- Активные судебные дела: {courts.get('activeCases', 0)}\n"
            f"- Завершённые: {courts.get('completedCases', 0)}"
        )

    lseg_section = MISSING
    if lseg:
        lseg_section = (
            f"- Компания: {(lseg.get('sanctions') or {}).get('isOnList', False)} "
            f"(совпадений: {len(company_hits)})\n"
            f"{sanction_text}\n"
            f"- PEP директор: {(lseg.get('pep') or {}).get('isHit', False)} "
            f"(совпадений: {len(director_hits)})\n"
            f"- Adverse media: {(lseg.get('adverseMedia') or {}).get('negativeCount', 0)} негативных статей"
        )

    score_line = (
        f"Балл: {total_score}."
        if total_score is not None
        else MISSING
    )

    return f"""# Комплексный отчёт по {company_name}

## 1. Резюме
{summary}
{director_line} {status_line}
LSEG: {f'совпадений по компании/директору — {len(company_hits) + len(director_hits)}; санкционных аффилиатов — {ext_sanctioned}.' if lseg else MISSING}
Нерезидентов в Adata: {len(non_residents_data) if non_residents_data else MISSING}.

## 1.1. Результаты автоматической проверки
{audit_narrative}

## 2. Итоговый риск-уровень: {risk_label}
{score_line} {summary}

## 3. Матрица рисков

### Финансовые риски
{tax_section}

### Санкционные риски
{flags_text}

**Проверка LSEG World-Check One (автоматическая):**
{lseg_section}

**Связанные лица (учредители / аффилиаты / нерезиденты), проверенные в LSEG:**
{lseg_ext_text}

### Репутационные риски
{courts_section or MISSING}

### Структурные риски
{flags_text}

## 4. Бенефициарная структура (UBO)
{ubo_text}

## 5. Аффилированные нерезиденты
{nr_text}
LSEG скрининг нерезидентов:
{lseg_ext_text}

## 6. Сеть аффилиатов директора/учредителей
{rel_text}

## 6.1. Анализ аффилиатов (рекурсивный, глубина 2)
{affiliate_analysis}

## 7. Рекомендация
{recommendation}
{rec_reason}
"""


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
    sources_hint = (
        "\n".join(f"- {s}" for s in sources_list) if sources_list else MISSING
    )
    report = ""
    append_case_event(
        case_id,
        provider="AI",
        action="full_report:start",
        subject={"type": "case", "value": case_id, "name": company_name},
        outcome={"status": "ok", "meta": {"availableBlocks": sources_list}},
    )

    if settings.openai_api_key:
        try:
            from app.services.ai.langfuse_setup import ai_trace, create_async_openai_client

            case_iin = str(row.get("iin") or "").strip()
            with ai_trace(name="full_report", iin=case_iin, case_id=case_id):
                client = create_async_openai_client()

                sections: dict[str, str] = {}

                async def _run_structure_hybrid() -> tuple[str, str]:
                    approx_tokens = len(_build_structure_conclusion_context(row)) // 4
                    logger.info(
                        "Full report section [structure]: ~%d tokens for case %s",
                        approx_tokens,
                        case_id,
                    )
                    try:
                        result = await _generate_structure_section_hybrid(
                            client, row, company_name
                        )
                        append_case_event(
                            case_id,
                            provider="AI",
                            action="full_report:section:structure",
                            outcome={
                                "status": "ok",
                                "meta": {
                                    "mode": "hybrid_dossiers_llm",
                                    "approxTokens": approx_tokens,
                                    "availableBlocks": sources_list,
                                },
                            },
                        )
                        return "structure", result
                    except Exception as exc:
                        logger.warning(
                            "Structure hybrid failed for %s: %s", case_id, exc
                        )
                        append_case_event(
                            case_id,
                            provider="AI",
                            action="full_report:section:structure",
                            outcome={
                                "status": "error",
                                "meta": {
                                    "mode": "template_fallback",
                                    "approxTokens": approx_tokens,
                                    "availableBlocks": sources_list,
                                },
                                "message": str(exc)[:200],
                            },
                        )
                        return "structure", _normalize_section_output(
                            "structure",
                            _build_structure_dossiers_block(row),
                        )

                async def _run_courts_hybrid() -> tuple[str, str]:
                    approx_tokens = len(_build_courts_conclusion_context(row)) // 4
                    logger.info(
                        "Full report section [courts]: ~%d tokens for case %s",
                        approx_tokens,
                        case_id,
                    )
                    try:
                        result = await _generate_courts_section_hybrid(
                            client, row, company_name
                        )
                        append_case_event(
                            case_id,
                            provider="AI",
                            action="full_report:section:courts",
                            outcome={
                                "status": "ok",
                                "meta": {
                                    "mode": "hybrid_table_llm",
                                    "approxTokens": approx_tokens,
                                    "availableBlocks": sources_list,
                                },
                            },
                        )
                        return "courts", result
                    except Exception as exc:
                        logger.warning(
                            "Courts hybrid failed for %s: %s", case_id, exc
                        )
                        append_case_event(
                            case_id,
                            provider="AI",
                            action="full_report:section:courts",
                            outcome={
                                "status": "error",
                                "meta": {
                                    "mode": "template_fallback",
                                    "approxTokens": approx_tokens,
                                    "availableBlocks": sources_list,
                                },
                                "message": str(exc)[:200],
                            },
                        )
                        return "courts", _format_courts_section(row)

                async def _run_section(section: str) -> tuple[str, str]:
                    ctx = _build_section_context(row, section)
                    approx_tokens = len(ctx) // 4
                    logger.info(
                        "Full report section [%s]: ~%d tokens for case %s",
                        section, approx_tokens, case_id,
                    )
                    try:
                        result = await _call_llm_section(client, section, ctx, company_name)
                        append_case_event(
                            case_id,
                            provider="AI",
                            action=f"full_report:section:{section}",
                            outcome={
                                "status": "ok",
                                "meta": {"mode": "llm", "approxTokens": approx_tokens, "availableBlocks": sources_list},
                            },
                        )
                        return section, result
                    except Exception as exc:
                        logger.warning("OpenAI section %s failed for %s: %s", section, case_id, exc)
                        append_case_event(
                            case_id,
                            provider="AI",
                            action=f"full_report:section:{section}",
                            outcome={
                                "status": "error",
                                "meta": {"mode": "template_fallback", "approxTokens": approx_tokens, "availableBlocks": sources_list},
                                "message": str(exc)[:200],
                            },
                        )
                        return section, _normalize_section_output(section, _template_section_fallback(row, section))

                import asyncio as _asyncio
                async def _run_sanctions_hybrid() -> tuple[str, str]:
                    approx_tokens = len(_build_sanctions_llm_context(row)) // 4
                    logger.info(
                        "Full report section [sanctions]: ~%d tokens for case %s",
                        approx_tokens,
                        case_id,
                    )
                    try:
                        result = await _generate_sanctions_section_hybrid(
                            client, row, company_name
                        )
                        append_case_event(
                            case_id,
                            provider="AI",
                            action="full_report:section:sanctions",
                            outcome={
                                "status": "ok",
                                "meta": {
                                    "mode": "hybrid_lseg_llm",
                                    "approxTokens": approx_tokens,
                                    "availableBlocks": sources_list,
                                },
                            },
                        )
                        return "sanctions", result
                    except Exception as exc:
                        logger.warning(
                            "Sanctions hybrid failed for %s: %s", case_id, exc
                        )
                        append_case_event(
                            case_id,
                            provider="AI",
                            action="full_report:section:sanctions",
                            outcome={
                                "status": "error",
                                "meta": {
                                    "mode": "template_fallback",
                                    "approxTokens": approx_tokens,
                                    "availableBlocks": sources_list,
                                },
                                "message": str(exc)[:200],
                            },
                        )
                        return "sanctions", _normalize_sanctions_output(
                            _build_sanctions_facts_block(row)
                        )

                parallel_results = await _asyncio.gather(
                    _run_courts_hybrid(),
                    _run_structure_hybrid(),
                    _run_sanctions_hybrid(),
                )
                for sec_name, sec_text in parallel_results:
                    sections[sec_name] = sec_text

                summary_context = _build_section_context(
                    row, "summary", section_excerpts=sections
                )
                try:
                    summary = await _call_llm_section(
                        client, "summary", summary_context, company_name
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
                    logger.warning(
                        "OpenAI summary failed for %s: %s", case_id, exc
                    )
                    summary = _template_section_fallback(row, "summary")
                    append_case_event(
                        case_id,
                        provider="AI",
                        action="full_report:section:summary",
                        outcome={
                            "status": "error",
                            "meta": {"mode": "template_fallback", "availableBlocks": sources_list},
                            "message": str(exc)[:200],
                        },
                    )

                report = _combine_sectional_report(
                    company_name, summary, sections, sources_hint, row=row
                )
        except Exception as exc:
            logger.warning(
                "OpenAI sectional full report failed for %s: %s", case_id, exc
            )
            append_case_event(
                case_id,
                provider="AI",
                action="full_report:openai_error",
                outcome={"status": "error", "message": str(exc)[:200]},
            )

    if not report:
        report = _template_full_report(row)
        append_case_event(
            case_id,
            provider="AI",
            action="full_report:template",
            outcome={"status": "ok", "meta": {"mode": "template", "availableBlocks": sources_list}},
        )

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
