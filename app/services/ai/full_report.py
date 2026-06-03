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

SYSTEM_PROMPT_SANCTIONS = """Ты — комплаенс-аналитик. Составь раздел «Санкционный анализ» по ТОЛЬКО предоставленным данным LSEG.

ПРАВИЛА:
1. Используй ИСКЛЮЧИТЕЛЬНО данные из контекста. Не выдумывай факты.
2. Если данных нет — пиши «Данные отсутствуют».
3. Охвати: санкции по компании, PEP директора, расширенный скрининг аффилиатов/нерезидентов.
4. Если чисто — кратко одной фразой. Если есть совпадения — детально с указанием списков и силы совпадения.
5. Отвечай на русском. Только Markdown, без HTML-тегов.
6. Не пиши заголовок раздела — только содержание.
7. Формат:
   - короткие абзацы до 260 символов;
   - списки с маркерами "- ", не более 6 пунктов в подразделе;
   - никаких длинных «простыней» текста.
8. ОБЯЗАТЕЛЬНО в конце добавь блок:
### Краткое сведение
- Ключевой вывод: ...
- Риск: green flag | yellow flag | red flag
- Следующее действие: ..."""

SYSTEM_PROMPT_COURTS = """Ты — комплаенс-аналитик. Составь раздел «Судебные дела и риски» по ТОЛЬКО предоставленным данным.

ПРАВИЛА:
1. Используй ИСКЛЮЧИТЕЛЬНО данные из контекста. Не выдумывай факты.
2. Охвати судебные дела компании и персональные дела директора/аффилиатов.
3. Для документов используй Markdown-ссылки [имя файла](url) из контекста.
4. Укажи налоговые риски, если они есть в контексте.
5. Если дел нет — одна фраза. Если есть — перечисли ключевые с оценкой риска.
6. Отвечай на русском. Только Markdown, без HTML-тегов.
7. Не пиши заголовок раздела — только содержание.
8. Формат:
   - короткие абзацы до 260 символов;
   - списки с маркерами "- ", не более 7 пунктов в подразделе;
   - ссылки на документы оставляй в Markdown-виде.
9. ОБЯЗАТЕЛЬНО в конце добавь блок:
### Краткое сведение
- Ключевой вывод: ...
- Риск: green flag | yellow flag | red flag
- Следующее действие: ..."""

SYSTEM_PROMPT_STRUCTURE = """Ты — комплаенс-аналитик. Составь раздел «Структура и аффилиаты» по ТОЛЬКО предоставленным данным.

ПРАВИЛА:
1. Используй ИСКЛЮЧИТЕЛЬНО данные из контекста. Не выдумывай факты.
2. Охвати: дерево аффилиатов, профили L1, бенефициаров, связи через директора/учредителей.
3. Если структура прозрачна — кратко. Если есть риски — детально.
4. Отвечай на русском. Только Markdown, без HTML-тегов.
5. Не пиши заголовок раздела — только содержание.
6. Формат:
   - короткие абзацы до 260 символов;
   - списки с маркерами "- ", не более 7 пунктов в подразделе.
7. ОБЯЗАТЕЛЬНО в конце добавь блок:
### Краткое сведение
- Ключевой вывод: ...
- Риск: green flag | yellow flag | red flag
- Следующее действие: ..."""

SYSTEM_PROMPT_SUMMARY = """Ты — комплаенс-аналитик. Составь Executive Summary (резюме) на 5-7 предложений.

ПРАВИЛА:
1. Используй выжимки из секций и итоговый балл/уровень риска из контекста.
2. Укажи ключевые риски и рекомендацию (одобрить / доп. проверка / отказать).
3. Не выдумывай факты — только то, что есть в контексте.
4. Отвечай на русском. Только Markdown, без HTML-тегов.
5. Не пиши заголовок — только текст резюме."""

_SECTION_PROMPTS: dict[str, str] = {
    "sanctions": SYSTEM_PROMPT_SANCTIONS,
    "courts": SYSTEM_PROMPT_COURTS,
    "structure": SYSTEM_PROMPT_STRUCTURE,
    "summary": SYSTEM_PROMPT_SUMMARY,
}

_SECTION_MAX_CHARS: dict[str, int] = {
    "sanctions": 8000,
    "courts": 10000,
    "structure": 8000,
    "summary": 6000,
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
        ("individualCourts", "Adata персональные судебные дела (ИИН)"),
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


def _format_lseg_extended_entity(entity: dict[str, Any], key: str) -> list[str]:
    """Format one lsegExtended entry; clean entities get a single line."""
    name = entity.get("name") or key
    role = entity.get("role") or "связанное лицо"
    country = entity.get("country") or MISSING
    on_list = entity.get("isOnSanctionList", False)
    hits = entity.get("hits") or []

    if not on_list and not hits:
        return [f"  • «{name}» ({role}, {country}) — чисто"]

    lists = ", ".join(entity.get("sanctionLists") or []) or "нет"
    status = "ПОД САНКЦИЯМИ" if on_list else "совпадения"
    lines = [f"  • «{name}» ({role}, {country}) — {status}, списки: {lists}"]

    for h in hits[:2]:
        wc1_name = h.get("primaryName") or h.get("submittedName") or name
        strength = h.get("matchStrength") or MISSING
        score = h.get("matchScore") if h.get("matchScore") is not None else MISSING
        hit_countries = ", ".join(h.get("countryNames") or h.get("countries") or []) or MISSING
        hit_lists = ", ".join(h.get("sanctionLists") or []) or "нет"
        if h.get("isSanction"):
            hit_status = "формальные санкции"
        elif h.get("isMaterialMatch"):
            hit_status = "сильное совпадение (watchlist)"
        else:
            hit_status = "совпадение"
        lines.append(
            f"    WC1: {wc1_name} — {hit_status}, {strength} (score {score}), "
            f"страна: {hit_countries}, списки: {hit_lists}"
        )
    return lines


def _format_lseg_extended_block(lseg_extended: dict[str, Any], *, max_entities: int = 20) -> str:
    """Human-readable block for all lsegExtended entities."""
    if not lseg_extended:
        return MISSING

    lines: list[str] = [
        f"Расширенный LSEG-скрининг: проверено связанных лиц — {len(lseg_extended)}.",
    ]
    clean_names: list[str] = []
    shown = 0
    for key, entity in lseg_extended.items():
        if not isinstance(entity, dict):
            continue
        on_list = entity.get("isOnSanctionList", False)
        hits = entity.get("hits") or []
        if not on_list and not hits:
            name = entity.get("name") or key
            clean_names.append(str(name))
            continue
        if shown >= max_entities:
            continue
        lines.extend(_format_lseg_extended_entity(entity, key))
        shown += 1
    if clean_names:
        preview = ", ".join(clean_names[:8])
        extra = len(clean_names) - 8
        suffix = f" и ещё {extra}" if extra > 0 else ""
        lines.append(f"  • Прочие ({len(clean_names)}) — чисто: {preview}{suffix}")
    return "\n".join(lines)


def _format_lseg_screening_summary(enriched: dict[str, Any]) -> str:
    """Human-readable narrative of automated LSEG checks for reports and LLM context."""
    lseg = enriched.get("lseg")
    if not _is_populated(lseg):
        return MISSING

    lseg = lseg or {}
    lseg_extended = enriched.get("lsegExtended") or {}
    screened_at = lseg.get("screenedAt") or MISSING
    lines: list[str] = [
        "Автоматическая проверка выполнена через LSEG World-Check One "
        f"(дата скрининга: {screened_at}).",
    ]

    company_hits = (lseg.get("sanctions") or {}).get("hits") or []
    if company_hits:
        lines.append("По основной компании обнаружены совпадения в базе WC1:")
        for h in company_hits[:3]:
            name = h.get("primaryName") or h.get("submittedName") or MISSING
            strength = h.get("matchStrength") or MISSING
            score = h.get("matchScore") or MISSING
            lists = ", ".join(h.get("sanctionLists") or []) or MISSING
            countries = ", ".join(h.get("countryNames") or h.get("countries") or []) or MISSING
            if h.get("isSanction"):
                status = "формальные санкционные списки"
            elif h.get("isMaterialMatch"):
                status = "сильное совпадение (watchlist / regulatory)"
            else:
                status = "совпадение"
            lines.append(
                f"  • {name} — {status}, {strength} (score {score}), "
                f"страна: {countries}, списки: {lists}"
            )
    else:
        lines.append(
            "По основной компании в санкционных списках WC1 "
            "формальных совпадений не зафиксировано."
        )

    pep = lseg.get("pep") or {}
    if pep.get("isHit"):
        lines.append("По директору/руководству выявлены PEP-совпадения в LSEG.")
        for h in (pep.get("individuals") or [])[:3]:
            lines.append(
                f"  • PEP: {h.get('primaryName', MISSING)} ({h.get('matchStrength', '')})"
            )
    else:
        lines.append("PEP-совпадений по директору в LSEG не выявлено.")

    if lseg_extended:
        lines.append(_format_lseg_extended_block(lseg_extended))
    else:
        lines.append(
            "Расширенный LSEG-скрининг аффилиатов/нерезидентов не выполнялся "
            "или не дал объектов для проверки."
        )

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
        if not isinstance(case, dict):
            continue
        category = case.get("category") or case.get("type") or "—"
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
        }
        rows.append(row_item)

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
                if not isinstance(case, dict):
                    continue
                case_role = _extract_case_role_by_parties(case, person_name)
                category = case.get("category") or case.get("type") or "—"
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
                }
                rows.append(row_item)
    return rows


def _court_row_risk_score(item: dict[str, Any]) -> int:
    score = 0
    if item.get("is_defendant"):
        score += 4
    if item.get("is_top_officer"):
        score += 3
    if item.get("is_serious"):
        score += 3
    if item.get("is_unresolved"):
        score += 2
    return score


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


def _format_courts_section(row: dict[str, Any], *, max_rows: int = 8) -> str:
    rows = _collect_court_rows(row)
    company_name = row.get("company_name") or "Компания"
    if not rows:
        return (
            "Судебные дела по компании и связанным лицам не обнаружены.\n\n"
            "### Вердикт ИИ по судам\n"
            "- Уровень риска: green\n"
            "- Почему:\n"
            "  - Данные судебных дел отсутствуют или не содержат риск-событий.\n"
            "- Влияние на компанию: Низкая релевантность — прямые судебные риски не выявлены.\n"
            "- Следующее действие:\n"
            "  - Продолжать плановый мониторинг изменений."
        )

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
        lines.append(f"Прочее: {hidden_count} дел.")

    verdict_level, why, impact, actions = _build_courts_verdict(rows_sorted)
    lines.extend(
        [
            "",
            "### Вердикт ИИ по судам",
            f"- Уровень риска: {verdict_level}",
            "- Почему:",
        ]
    )
    for item in why[:3]:
        lines.append(f"  - {_short_text(item, max_len=190)}")
    lines.append(f"- Влияние на компанию: {_short_text(impact, max_len=220)}")
    lines.append("- Следующее действие:")
    for action in actions[:2]:
        lines.append(f"  - {_short_text(action, max_len=170)}")
    return "\n".join(lines)


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
        parts = [
            f"# {company_name} (БИН {iin})",
            f"Уровень риска: {assessment.get('riskLevel') or row.get('risk_level') or MISSING}",
        ]
        lseg_text = _format_lseg_screening_summary(
            {**enriched, "_company_name": company_name}
        )
        parts.append(f"\n## LSEG ПРОВЕРКА\n{lseg_text}")
        flags = assessment.get("flags") or []
        if flags:
            flag_text = "\n".join(
                f"- [{f.get('severity', '')}] {f.get('message', '')}" for f in flags[:5]
            )
            parts.append(f"\n## ФЛАГИ ОЦЕНКИ\n{flag_text}")
        risk_flags = enrichment.get("riskFlags") or []
        if risk_flags:
            parts.append(
                "\n## ФАКТОРЫ РИСКА (Adata)\n"
                + "\n".join(f"- {f}" for f in risk_flags[:8])
            )
        return _truncate_context("\n".join(parts), max_chars=max_chars)

    if section == "courts":
        return _truncate_context(_format_courts_section(row), max_chars=max_chars)

    if section == "structure":
        parts = [f"# {company_name} (БИН {iin})"]
        affiliate_tree = enriched.get("affiliateTree")
        if _is_populated(affiliate_tree) and isinstance(affiliate_tree, dict):
            tree_text = "\n".join(
                [
                    f"Статус: {affiliate_tree.get('status', MISSING)}",
                    f"Узлов: {affiliate_tree.get('nodesCount', 0)}",
                    _format_affiliate_tree_compact(affiliate_tree),
                ]
            )
            parts.append(f"\n## ДЕРЕВО АФФИЛИАТОВ\n{tree_text}")

        affiliate_enrichments = _collect_affiliate_enrichments(affiliate_tree, max_depth=2)
        affiliate_analysis = _format_affiliate_analysis(affiliate_enrichments)
        parts.append(f"\n## АНАЛИЗ АФФИЛИАТОВ\n{affiliate_analysis}")

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
                excerpt = (section_excerpts.get(key) or "")[:1500]
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
        lseg = enriched.get("lseg")
        if lseg:
            return _format_lseg_screening_summary(
                {**enriched, "_company_name": company_name}
            )
        flags = assessment.get("flags") or []
        if flags:
            return "\n".join(f"- {f.get('message', '')}" for f in flags[:5])
        return "Санкционные данные LSEG отсутствуют."

    if section == "courts":
        return _format_courts_section(row)

    if section == "structure":
        affiliate_tree = enriched.get("affiliateTree")
        affiliate_enrichments = _collect_affiliate_enrichments(affiliate_tree, max_depth=2)
        tree_part = ""
        if _is_populated(affiliate_tree) and isinstance(affiliate_tree, dict):
            tree_part = _format_affiliate_tree_compact(affiliate_tree)
        analysis = _format_affiliate_analysis(affiliate_enrichments)
        return f"{tree_part}\n\n{analysis}".strip() or "Данные по структуре отсутствуют."

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


def _extract_key_findings(text: str, *, max_items: int = 2) -> list[str]:
    findings: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### Краткое сведение"):
            break
        if line.startswith(("- ", "* ")):
            candidate = line[2:].strip()
            if candidate:
                findings.append(candidate[:170])
        elif line and not line.startswith("#") and len(line) > 20:
            findings.append(line[:170])
        if len(findings) >= max_items:
            break
    if findings:
        return findings[:max_items]
    return _split_sentences(text, limit=max_items)


def _infer_risk_tag(section: str, text: str) -> str:
    lowered = text.lower()
    red_markers = (
        "санкц",
        "pep",
        "ответчик",
        "уголов",
        "высок",
        "критич",
        "задолж",
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
    if section == "courts":
        return _sanitize_llm_text(text or "").strip() or MISSING
    base = _sanitize_llm_text(text or "").strip()
    readable = _make_readable_markdown(base)
    return _append_takeaway_block(section, readable)


def _combine_sectional_report(
    company_name: str,
    summary: str,
    sections: dict[str, str],
    sources_hint: str,
) -> str:
    sanctions = _normalize_section_output("sanctions", sections.get("sanctions", MISSING))
    courts = _normalize_section_output("courts", sections.get("courts", MISSING))
    structure = _normalize_section_output("structure", sections.get("structure", MISSING))
    return (
        f"# Отчёт\n\n"
        f"## Резюме\n{summary.strip()}\n\n"
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
        "sanctions": f"Составь раздел санкционного анализа для «{company_name}».",
        "courts": f"Составь раздел судебных дел и рисков для «{company_name}».",
        "structure": f"Составь раздел структуры и аффилиатов для «{company_name}».",
        "summary": f"Составь executive summary для «{company_name}».",
    }
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"{context}\n\n{user_prompts[section]}",
            },
        ],
        temperature=0.2,
        max_tokens=1200 if section == "summary" else 1500,
    )
    content = response.choices[0].message.content or ""
    return _normalize_section_output(section, content) if section != "summary" else _sanitize_llm_text(content)


def _format_affiliate_analysis(affiliates: list[dict]) -> str:
    if not affiliates:
        return "Данные по аффилиатам отсутствуют или не загружены."

    lines: list[str] = []
    for aff in affiliates:
        name = aff["name"]
        iin_bin = aff["iinBin"]
        role = aff["role"]
        risk = aff.get("riskLevel") or "не определён"

        if _is_low_risk_affiliate(aff):
            lines.append(
                f"- {name} (БИН `{iin_bin}`, {role or '—'}) — низкий риск, чисто"
            )
            continue

        lines.append(f"\n### {name} (БИН: {iin_bin})")

        lines.append(f"- **Роль:** {role or '—'}")
        lines.append(f"- **Уровень риска:** {risk}")

        if aff.get("director"):
            lines.append(f"- **Директор:** {aff['director']}")

        courts = aff.get("courts") or {}
        if courts:
            active = courts.get("activeCases", 0)
            total_amt = courts.get("totalAmount", 0) or 0
            lines.append(
                f"- **Судебные дела:** активных {active}, сумма {total_amt:,.0f} тг".replace(
                    ",", "\u202f"
                )
            )
            for case in (courts.get("cases") or [])[:3]:
                lines.append(f"  - {_format_court_case_line(case).lstrip('- ')}")
        else:
            lines.append("- **Судебные дела:** нет данных")

        taxes = aff.get("taxes") or {}
        if taxes:
            status = taxes.get("status", "")
            debt = taxes.get("debt", 0) or 0
            lines.append(
                f"- **Налоги:** статус={status}, задолженность={debt:,.0f} тг".replace(
                    ",", "\u202f"
                )
            )

        flags = aff.get("riskFlags") or []
        if flags:
            lines.append(f"- **Риск-флаги:** {'; '.join(str(f) for f in flags)}")

        lseg = aff.get("lseg")
        if lseg:
            san = lseg.get("sanctions") or {}
            pep = lseg.get("pep") or {}
            if san.get("isOnList"):
                matched = san.get("matchedLists") or []
                lines.append(f"- **LSEG САНКЦИИ:** {', '.join(matched[:3])}")
            if pep.get("isHit"):
                lines.append("- **LSEG PEP:** обнаружено совпадение")
            if not san.get("isOnList") and not pep.get("isHit"):
                lines.append("- **LSEG:** чисто")
        else:
            lines.append("- **LSEG:** не проверялось")

        sanctions = aff.get("sanctions") or {}
        if sanctions.get("isOnList"):
            lists = sanctions.get("lists") or []
            lines.append(f"- **Adata санкции/риски:** {', '.join(str(x) for x in lists[:3])}")

    return "\n".join(lines)


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
    # Target ~5800 chars so total request stays under 8000 TPM with system prompt.
    return _truncate_context(context, max_chars=5800)


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
            from openai import AsyncOpenAI

            client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
            if settings.openai_base_url:
                client_kwargs["base_url"] = settings.openai_base_url
            client = AsyncOpenAI(**client_kwargs)

            section_names = ("sanctions", "courts", "structure")
            sections: dict[str, str] = {}

            for section in section_names:
                if section == "courts":
                    sections[section] = _format_courts_section(row)
                    append_case_event(
                        case_id,
                        provider="AI",
                        action=f"full_report:section:{section}",
                        outcome={
                            "status": "ok",
                            "meta": {
                                "mode": "deterministic_heuristic",
                                "availableBlocks": sources_list,
                            },
                        },
                    )
                    continue
                context = _build_section_context(row, section)
                approx_tokens = len(context) // 4
                logger.info(
                    "Full report section [%s]: ~%d tokens for case %s",
                    section,
                    approx_tokens,
                    case_id,
                )
                try:
                    sections[section] = await _call_llm_section(
                        client, section, context, company_name
                    )
                    append_case_event(
                        case_id,
                        provider="AI",
                        action=f"full_report:section:{section}",
                        outcome={
                            "status": "ok",
                            "meta": {
                                "mode": "llm",
                                "approxTokens": approx_tokens,
                                "availableBlocks": sources_list,
                            },
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "OpenAI section %s failed for %s: %s",
                        section,
                        case_id,
                        exc,
                    )
                    sections[section] = _normalize_section_output(
                        section, _template_section_fallback(row, section)
                    )
                    append_case_event(
                        case_id,
                        provider="AI",
                        action=f"full_report:section:{section}",
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
                company_name, summary, sections, sources_hint
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
    db.update_case(case_id, enriched_data=save_enriched)

    logger.info("Full report saved for case %s", case_id)
    append_case_event(
        case_id,
        provider="AI",
        action="full_report:saved",
        outcome={"status": "ok"},
    )
    return report
