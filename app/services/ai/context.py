"""Build a structured text dossier for the compliance AI assistant."""

from __future__ import annotations

from typing import Any


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


def context_as_json_snippet(context: str, *, max_chars: int = 24_000) -> str:
    """Trim very long context for token limits."""
    if len(context) <= max_chars:
        return context
    return context[:max_chars] + "\n\n… (контекст обрезан по лимиту)"
