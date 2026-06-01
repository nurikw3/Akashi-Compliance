from app.services.enrichment.person import normalize_person_name


def test_normalize_person_name_rejects_json_blob() -> None:
    blob = {
        "terrorist": False,
        "litigation": {"total_civil_count": 1},
        "fullname_director": "УСПАНОВ РУСТЕМ КАЙРАТОВИЧ",
    }
    assert normalize_person_name(blob) == "УСПАНОВ РУСТЕМ КАЙРАТОВИЧ"


def test_normalize_person_name_rejects_stringified_dict() -> None:
    assert normalize_person_name("{'terrorist': False}") is None


def test_normalize_person_name_accepts_plain_string() -> None:
    assert normalize_person_name("  Иванов И.И.  ") == "Иванов И.И."
