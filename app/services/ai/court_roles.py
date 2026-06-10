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
        # Точное совпадение ФИО либо совпадение фамилии как отдельного слова
        # (а не подстроки — чтобы «Ким» не совпадал с «Кимаев»).
        if name_key == party_key or (surname and surname in party_key.split()):
            return True
    return False


def party_list_role_for_person(case: dict[str, Any], person_name: str) -> str | None:
    name_key = normalize_person_name_key(person_name)
    if party_list_contains_person(name_key, case.get("defendants") or []):
        return "Ответчик"
    if party_list_contains_person(name_key, case.get("plaintiffs") or []):
        return "Истец"
    return None


# Исход дела, означающий взыскание/осуждение стороны (не «третьего лица»).
_SANCTION_OUTCOME_RE = re.compile(
    r"обвинительн\w*\s+приговор|признан\w*\s+виновн|осужд|"
    r"наложени\w*\s+(?:админист\w*\s+)?взыскан",
    re.IGNORECASE,
)


def _case_sanction_outcome(case: dict[str, Any]) -> bool:
    text = " ".join(str(case.get(k) or "") for k in ("result", "status"))
    return bool(_SANCTION_OUTCOME_RE.search(text))


def resolve_person_case_role(case: dict[str, Any], person_name: str) -> dict[str, Any]:
    """
    Объединяет role из Adata и фактическое присутствие ФИО в данных дела.

    - display_role: для таблицы/отчёта
    - adata_role: роль по полю Adata `role`
    - party_list_role: роль по спискам defendants/plaintiffs
    - in_participants: ФИО присутствует в списке участников дела
    - has_discrepancy: поле `role` противоречит фактическим данным API
    """
    adata_role = normalize_case_role(case.get("role"))
    party_role = party_list_role_for_person(case, person_name)
    name_key = normalize_person_name_key(person_name)
    in_participants = party_list_contains_person(
        name_key, case.get("participants") or []
    )
    sanction_outcome = _case_sanction_outcome(case)

    # Классическое расхождение: роль Adata ≠ роль по спискам сторон.
    list_discrepancy = bool(
        adata_role != "Не указано" and party_role and adata_role != party_role
    )

    # «Третья сторона», но человек сам числится участником дела (часто единственным)
    # — третье лицо не является стороной; роль требует сверки.
    third_party_conflict = adata_role == "Третья сторона" and in_participants

    has_discrepancy = bool(list_discrepancy or third_party_conflict)

    if list_discrepancy:
        display_role = (
            f"{adata_role} (в списке сторон: {party_role} — сверить с материалами дела)"
        )
    elif third_party_conflict:
        if sanction_outcome:
            note = "числится участником дела, по которому вынесено взыскание/приговор"
        else:
            note = "числится среди участников дела"
        display_role = f"Третья сторона ({note} — сверить роль)"
    elif adata_role != "Не указано":
        display_role = adata_role
    elif party_role:
        display_role = f"{party_role} (роль Adata не указана)"
    else:
        display_role = "Не указано"

    return {
        "adata_role": adata_role,
        "party_list_role": party_role,
        "in_participants": in_participants,
        "has_discrepancy": has_discrepancy,
        "display_role": display_role,
    }
