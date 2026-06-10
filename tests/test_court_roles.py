from app.services.ai.court_roles import resolve_person_case_role
from app.services.ai.full_report import _contract_relevance_tier, _extract_case_role_by_parties


def test_discrepancy_third_party_in_defendants_list():
    person = "НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ"
    case = {
        "role": "Третья сторона",
        "category": "Статья 73. Противоправные действия в сфере семейно-бытовых отношений",
        "defendants": [person, "ИВАНОВ И.И."],
    }
    resolved = resolve_person_case_role(case, person)
    assert resolved["adata_role"] == "Третья сторона"
    assert resolved["party_list_role"] == "Ответчик"
    assert resolved["has_discrepancy"] is True
    # Расхождение показывается текстом на русском, без эмодзи.
    assert "⚠️" not in resolved["display_role"]
    assert "в списке сторон" in resolved["display_role"]
    assert "Ответчик" in resolved["display_role"]
    assert _contract_relevance_tier(
        case, person, person_role="Директор основной компании"
    ) == "yellow"
    assert "в списке сторон" in _extract_case_role_by_parties(case, person)


def test_third_party_but_in_participants_is_discrepancy():
    """Adata role='Третья сторона', но человек сам в participants и по делу
    вынесено взыскание — это расхождение, требующее сверки."""
    person = "НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ"
    case = {
        "role": "Третья сторона",
        "category": "Статья 73. Противоправные действия в сфере семейно-бытовых отношений",
        "result": "вынесено постановление о наложении административного взыскания",
        "defendants": [],
        "plaintiffs": [],
        "participants": [person],
    }
    resolved = resolve_person_case_role(case, person)
    assert resolved["in_participants"] is True
    assert resolved["has_discrepancy"] is True
    assert "сверить роль" in resolved["display_role"]
    assert "взыскание" in resolved["display_role"]


def test_genuine_third_party_not_in_participants_no_discrepancy():
    """Человек НЕ в participants (там другие лица) — 'Третья сторона' корректна."""
    person = "АЛИБАЕВА ДИНА ИРИХСЕНОВНА"
    case = {
        "role": "Третья сторона",
        "category": "Статья 610. ДТП",
        "result": "вынесено постановление о наложении административного взыскания",
        "defendants": [],
        "plaintiffs": [],
        "participants": ["ЖҰМАБЕК МАҒЖАН БАҚЫТЖАНҰЛЫ"],
    }
    resolved = resolve_person_case_role(case, person)
    assert resolved["in_participants"] is False
    assert resolved["has_discrepancy"] is False
    assert resolved["display_role"] == "Третья сторона"


def test_consistent_defendant_no_discrepancy():
    person = "НУРУШЕВ АРМАН ЖАКЫПБЕКОВИЧ"
    case = {
        "role": "Ответчик",
        "category": "Статья 73",
        "defendants": [person],
    }
    resolved = resolve_person_case_role(case, person)
    assert resolved["has_discrepancy"] is False
    assert _contract_relevance_tier(
        case, person, person_role="Директор основной компании"
    ) == "red"
