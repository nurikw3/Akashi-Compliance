"""Согласование роли в деле: поле role (Adata) + списки defendants/plaintiffs."""

from __future__ import annotations

import re
from typing import Any


def normalize_person_name_key(raw_name: Any) -> str:
    return re.sub(r"\s+", " ", str(raw_name or "").strip().lower())


def normalize_case_role(raw_role: Any) -> str:
    role = str(raw_role or "").strip().lower()
    if not role:
        return "Не указано"
    if "ответ" in role or "defend" in role:
        return "Ответчик"
    if "ист" in role or "plaint" in role:
        return "Истец"
    if "треть" in role or "third" in role:
        return "Третья сторона"
    return str(raw_role or "Не указано").strip()[:40] or "Не указано"


def party_list_contains_person(name_key: str, parties: list[Any]) -> bool:
    if not name_key:
        return False
    surname = name_key.split()[0] if name_key.split() else ""
    for party in parties:
        party_key = normalize_person_name_key(party)
        if not party_key:
            continue
        if name_key == party_key or (surname and surname in party_key):
            return True
    return False


def party_list_role_for_person(case: dict[str, Any], person_name: str) -> str | None:
    name_key = normalize_person_name_key(person_name)
    if party_list_contains_person(name_key, case.get("defendants") or []):
        return "Ответчик"
    if party_list_contains_person(name_key, case.get("plaintiffs") or []):
        return "Истец"
    return None


def resolve_person_case_role(case: dict[str, Any], person_name: str) -> dict[str, Any]:
    """
    Объединяет role из Adata и попадание ФИО в списки сторон.

    - display_role: для таблицы/отчёта
    - adata_role: для red flag (только явный ответчик в Adata)
    - has_discrepancy: роль Adata ≠ список сторон — сигнал для ручной проверки
    """
    adata_role = normalize_case_role(case.get("role"))
    party_role = party_list_role_for_person(case, person_name)
    has_discrepancy = bool(
        adata_role != "Не указано"
        and party_role
        and adata_role != party_role
    )

    if has_discrepancy:
        display_role = (
            f"{adata_role} ⚠️ (в списке: {party_role} — сверить с материалами дела)"
        )
    elif adata_role != "Не указано":
        display_role = adata_role
    elif party_role:
        display_role = f"{party_role} (роль Adata не указана)"
    else:
        display_role = "Не указано"

    return {
        "adata_role": adata_role,
        "party_list_role": party_role,
        "has_discrepancy": has_discrepancy,
        "display_role": display_role,
    }
