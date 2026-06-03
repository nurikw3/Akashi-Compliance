from app.services.ai.context import normalize_person_iin, resolve_individual_courts_key


def test_normalize_person_iin_strips_spaces():
    assert normalize_person_iin("770502300236") == "770502300236"
    assert normalize_person_iin("770 502 300 236") == "770502300236"


def test_resolve_individual_courts_by_director_iin():
    enriched = {
        "enrichment": {"companyInfo": {"director_iin": "770502300236"}},
        "individualCourts": {"770502300236": [{"number": "1"}]},
        "individualCourtsMeta": {
            "770502300236": {"name": "НУРУШЕВ", "role": "Директор основной компании"}
        },
    }
    assert resolve_individual_courts_key(enriched) == "770502300236"
    assert resolve_individual_courts_key(enriched, "770502300236") == "770502300236"


def test_resolve_individual_courts_fuzzy_last_six():
    enriched = {
        "individualCourts": {"770502300236": [{"number": "1"}]},
    }
    assert resolve_individual_courts_key(enriched, "02300236") == "770502300236"
