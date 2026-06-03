"""Build a structured text dossier for the compliance AI assistant."""

from __future__ import annotations

from typing import Any

from app.services.ai.court_roles import resolve_person_case_role


def _lines(title: str, items: list[str]) -> list[str]:
    if not items:
        return []
    out = [f"\n### {title}"]
    out.extend(f"- {item}" for item in items)
    return out


def build_case_context(
    *,
    company_name: str,
    iin: str,
    enrichment: dict[str, Any] | None,
    assessment: dict[str, Any] | None,
    conclusion: str | None,
    data_sources: dict[str, str] | None = None,
) -> str:
    """Human-readable dossier for LLM and template replies."""
    parts = [
        f"# Досье контрагента: {company_name}",
        f"БИН/ИИН: {iin}",
    ]

    if data_sources:
        src = ", ".join(f"{k}={v}" for k, v in data_sources.items())
        parts.append(f"Источники данных: {src}")

    if not enrichment:
        parts.append("\nДанные обогащения ещё не загружены (дело в обработке).")
        if conclusion:
            parts.append(f"\n## Предварительное заключение\n{conclusion}")
        return "\n".join(parts)

    info = enrichment.get("companyInfo") or {}
    parts.append("\n## Регистрация и профиль")
    parts.extend(
        _lines(
            "Реквизиты",
            [
                f"Полное наименование: {info.get('fullName', '—')}",
                f"Статус: {info.get('operatingStatus', '—')}",
                f"Дата регистрации: {info.get('registrationDate', '—')}",
                f"Адрес: {info.get('address', '—')}",
                f"Директор: {info.get('director', '—')}",
                f"Сотрудников: {info.get('employees', '—')}",
                f"ОКЭД / отрасль: {info.get('industry', '—')}",
                *( [f"ОПФ: {info['legalForm']}"] if info.get("legalForm") else [] ),
                *( [f"Собственность: {info['ownership']}"] if info.get("ownership") else [] ),
                *( [f"Карточка Adata: {info['sourceLink']}"] if info.get("sourceLink") else [] ),
            ],
        )
    )

    status_flags = enrichment.get("statusFlags") or []
    parts.extend(_lines("Статус предприятия (флаги Adata)", status_flags))

    taxes = enrichment.get("taxes") or {}
    tax_lines = [
        f"Задолженность: {taxes.get('debt', 0):,.0f} тг".replace(",", " "),
        f"Статус налогов: {taxes.get('status', '—')}",
        f"Последний год отчислений: {taxes.get('lastPayment', '—')}",
    ]
    if taxes.get("totalPaid"):
        tax_lines.append(f"Всего уплачено (taxDeductions): {taxes['totalPaid']:,.0f} тг".replace(",", " "))
    yearly = taxes.get("yearlyPayments") or []
    for row in yearly[:6]:
        tax_lines.append(f"  {row.get('year')}: {row.get('amount', 0):,.0f} тг".replace(",", " "))
    parts.extend(_lines("Налоги", tax_lines))

    courts = enrichment.get("courts") or {}
    court_lines = [
        f"Область: {'руководитель' if courts.get('scope') == 'director' else 'компания'}",
        f"Активные дела (оценка): {courts.get('activeCases', 0)}",
        f"Завершённые: {courts.get('completedCases', 0)}",
    ]
    if courts.get("note"):
        court_lines.append(f"Примечание: {courts['note']}")
    for case in (courts.get("cases") or [])[:12]:
        court_lines.append(
            f"  {case.get('date', '')}: {case.get('type', '')} — {case.get('status', '')}"
        )
    parts.extend(_lines("Судебные дела", court_lines))

    risk_flags = enrichment.get("riskFlags") or []
    sanctions = enrichment.get("sanctions") or {}
    risk_lines = list(risk_flags)
    if sanctions.get("isOnList") and not risk_lines:
        risk_lines.extend(sanctions.get("lists") or ["Есть факторы риска"])
    if not risk_lines:
        risk_lines.append("Критические факторы riskFactor не выявлены")
    parts.extend(_lines("Факторы риска (riskFactor)", risk_lines))

    affiliates = enrichment.get("affiliates") or {}
    aff_lines: list[str] = []
    for co in (affiliates.get("companies") or [])[:25]:
        aff_lines.append(
            f"ЮЛ: {co.get('name', '—')} | БИН {co.get('iinBin', '—')} | {co.get('role', '')}"
        )
    for person in (affiliates.get("individuals") or [])[:15]:
        aff_lines.append(
            f"ФЛ: {person.get('name', '—')} | ИИН {person.get('iin', '—')} | {person.get('role', '')}"
        )
    if not aff_lines:
        aff_lines.append("Связанные лица не найдены")
    parts.extend(_lines("Аффилированность (connectedDiagram + founders)", aff_lines))

    contacts = enrichment.get("contacts") or {}
    contact_lines: list[str] = []
    for phone in (contacts.get("phones") or [])[:5]:
        contact_lines.append(f"Тел: {phone}")
    for email in (contacts.get("emails") or [])[:5]:
        contact_lines.append(f"Email: {email}")
    parts.extend(_lines("Контакты", contact_lines))

    req = enrichment.get("requisites") or {}
    if req:
        parts.extend(
            _lines(
                "Банковские реквизиты",
                [f"{k}: {v}" for k, v in req.items() if v],
            )
        )

    if assessment:
        parts.append("\n## Оценка комплаенс-системы")
        parts.append(f"Уровень риска: {assessment.get('riskLevel', '—')}")
        parts.append(f"Резюме: {assessment.get('summary', '—')}")
        parts.extend(_lines("Рекомендации", assessment.get("recommendations") or []))
        flag_msgs = [f.get("message", "") for f in (assessment.get("flags") or []) if f.get("message")]
        parts.extend(_lines("Флаги оценки", flag_msgs))

    if conclusion:
        parts.append(f"\n## Заключение ИИ\n{conclusion}")

    return "\n".join(parts)


def normalize_person_iin(value: Any) -> str | None:
    """12-digit IIN/BIN for individuals."""
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits if len(digits) == 12 else None


def resolve_individual_courts_key(
    enriched: dict[str, Any],
    iin_hint: str | None = None,
    *,
    enrichment: dict[str, Any] | None = None,
) -> str | None:
    """Find storage key in individualCourts for a person IIN (or director default)."""
    individual_courts = enriched.get("individualCourts")
    if not isinstance(individual_courts, dict) or not individual_courts:
        return None

    by_norm: dict[str, str] = {}
    for key in individual_courts:
        norm = normalize_person_iin(key)
        if norm:
            by_norm[norm] = key

    if iin_hint:
        norm = normalize_person_iin(iin_hint)
        if norm and norm in by_norm:
            return by_norm[norm]
        hint_digits = "".join(ch for ch in str(iin_hint) if ch.isdigit())
        if len(hint_digits) >= 6:
            for n, key in by_norm.items():
                if n.endswith(hint_digits[-6:]) or hint_digits.endswith(n[-6:]):
                    return key

    enrichment = enrichment or enriched.get("enrichment") or {}
    dir_iin = normalize_person_iin((enrichment.get("companyInfo") or {}).get("director_iin"))
    if dir_iin and dir_iin in by_norm:
        return by_norm[dir_iin]

    meta = enriched.get("individualCourtsMeta") or {}
    for key, m in meta.items():
        if isinstance(m, dict) and "директор" in str(m.get("role") or "").lower():
            if key in individual_courts:
                return key

    with_cases = [
        k
        for k, v in individual_courts.items()
        if isinstance(v, list) and len(v) > 0
    ]
    if len(with_cases) == 1:
        return with_cases[0]
    return None


def _format_individual_courts_short(enriched: dict[str, Any]) -> list[str]:
    """Топ дел по физлицам для контекста чата — только существенные."""
    lines: list[str] = []
    individual_courts = enriched.get("individualCourts")
    meta = enriched.get("individualCourtsMeta") or {}
    if not isinstance(individual_courts, dict):
        return lines

    _SERIOUS = ("семейно-бытов", "насили", "уголов", "ст.73", "статья 73", "хулиган")
    _NOISE = ("дтп", "610", "транспорт", "водител", "пдд")

    for iin_key, cases in individual_courts.items():
        if not isinstance(cases, list):
            continue
        person_meta = meta.get(iin_key) if isinstance(meta.get(iin_key), dict) else {}
        person_name = str(person_meta.get("name") or iin_key)
        person_role = str(person_meta.get("role") or "")

        serious_defendant = []
        serious_third_party = []
        other_defendant = []
        for case in cases:
            if not isinstance(case, dict):
                continue
            cat = str(case.get("category") or case.get("type") or "").lower()
            if any(n in cat for n in _NOISE):
                continue
            resolved = resolve_person_case_role(case, person_name)
            adata_role = resolved["adata_role"]
            is_serious = any(m in cat for m in _SERIOUS)
            if resolved["has_discrepancy"]:
                serious_third_party.append(case)
            elif is_serious and adata_role == "Ответчик":
                serious_defendant.append(case)
            elif is_serious and adata_role == "Третья сторона":
                serious_third_party.append(case)
            elif adata_role == "Ответчик":
                other_defendant.append(case)

        if not cases:
            continue
        label = person_name
        if person_role:
            label += f" ({person_role})"
        detail_parts: list[str] = []
        for case in serious_defendant[:2]:
            cat = case.get("category") or case.get("type") or "—"
            date = case.get("date") or "—"
            detail_parts.append(f"🔴 ответчик · {cat} · {date}")
        for case in serious_third_party[:2]:
            cat = case.get("category") or case.get("type") or "—"
            date = case.get("date") or "—"
            r = resolve_person_case_role(case, person_name)
            tag = "расхождение role/стороны" if r["has_discrepancy"] else "третья сторона"
            detail_parts.append(f"⚠️ {tag} · {cat} · {date}")
        for case in other_defendant[:2]:
            cat = case.get("category") or case.get("type") or "—"
            date = case.get("date") or "—"
            detail_parts.append(f"⚠️ ответчик · {cat} · {date}")
        summary = f"всего {len(cases)} дел в Adata"
        if detail_parts:
            lines.append(f"{label}: {summary}; {'; '.join(detail_parts)}")
        else:
            lines.append(f"{label}: {summary} (ДТП/ПДД и прочие — см. get_individual_courts)")

    return lines


def build_short_context(
    *,
    company_name: str,
    iin: str,
    enrichment: dict[str, Any] | None,
    assessment: dict[str, Any] | None,
    lseg: dict[str, Any] | None = None,
    enriched: dict[str, Any] | None = None,
) -> str:
    """Контекст чата: ключевые факты + суды с категориями. Детали — через tools."""
    parts = [f"Компания: {company_name} (БИН: {iin})"]

    if assessment:
        risk = assessment.get("riskLevel", "—")
        score = assessment.get("score") or assessment.get("totalScore")
        score_part = f", балл: {score}" if score else ""
        parts.append(f"Уровень риска: {risk}{score_part}")

    if enrichment:
        info = enrichment.get("companyInfo") or {}
        director = str(info.get("director") or "—")
        # убираем хвостовой «1.» если есть
        import re as _re
        director = _re.sub(r"\s+1\.?\s*$", "", director).strip()
        parts.append(f"Директор: {director}")
        director_iin = normalize_person_iin(info.get("director_iin"))
        if director_iin:
            parts.append(f"ИИН директора: {director_iin}")
        parts.append(f"Статус: {info.get('operatingStatus', '—')}")

        flags = enrichment.get("riskFlags") or []
        if flags:
            parts.append(f"Риск-флаги: {'; '.join(str(f) for f in flags[:4])}")

        courts = enrichment.get("courts") or {}
        active = courts.get("activeCases", 0)
        parts.append(
            f"Суды юрлица (агрегат Adata): активных {active} "
            f"(это не персональные дела директора)"
        )

        taxes = enrichment.get("taxes") or {}
        debt = taxes.get("debt", 0) or 0
        if debt > 0:
            parts.append(f"Налоговая задолженность: {debt:,.0f} тг".replace(",", "\u202f"))

        affiliates = enrichment.get("affiliates") or {}
        companies = [c.get("name") for c in (affiliates.get("companies") or [])[:6] if c.get("name")]
        if companies:
            parts.append(f"Учредители/аффилиаты: {', '.join(companies)}")

    # Суды физлиц (individualCourts в Postgres, не enrichment.courts)
    if enriched:
        court_lines = _format_individual_courts_short(enriched)
        if court_lines:
            parts.append("Персональные суды (individualCourts, кэш Adata):")
            parts.extend(f"  {l}" for l in court_lines)
        elif enrichment:
            key = resolve_individual_courts_key(enriched, enrichment=enrichment)
            ind = enriched.get("individualCourts") or {}
            if key and isinstance(ind.get(key), list) and ind[key]:
                parts.append(
                    f"Персональные суды директора: {len(ind[key])} дел — "
                    f"вызови get_individual_courts для деталей"
                )

    if lseg:
        san = lseg.get("sanctions") or {}
        pep = lseg.get("pep") or {}
        if san.get("isOnList"):
            hits = san.get("hits") or []
            names = [h.get("primaryName") or "" for h in hits[:2] if h.get("primaryName")]
            names_str = ", ".join(names) if names else "совпадения"
            parts.append(f"LSEG САНКЦИИ: {names_str}")
        elif (san.get("hits") or []):
            parts.append(f"LSEG: совпадения в WC1 ({len(san['hits'])})")
        else:
            parts.append("LSEG санкции: нет")
        if pep.get("isHit"):
            pep_names = [h.get("primaryName", "") for h in (pep.get("individuals") or [])[:2]]
            parts.append(f"LSEG PEP: {', '.join(pep_names) or 'выявлен'}")

    parts.append(
        "\nДетали: get_individual_courts (ИИН директора или без параметра), "
        "traverse_affiliate_graph, search_lseg_sanctions."
    )
    return "\n".join(parts)


def context_as_json_snippet(context: str, *, max_chars: int = 24_000) -> str:
    """Trim very long context for token limits."""
    if len(context) <= max_chars:
        return context
    return context[:max_chars] + "\n\n… (контекст обрезан по лимиту)"
