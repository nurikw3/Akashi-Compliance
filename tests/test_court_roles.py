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
    assert "⚠️" in resolved["display_role"]
    assert _contract_relevance_tier(
        case, person, person_role="Директор основной компании"
    ) == "yellow"
    assert "⚠️" in _extract_case_role_by_parties(case, person)


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
