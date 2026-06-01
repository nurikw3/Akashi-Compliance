from app.services.lseg.screening import filter_bin_query_false_positive_hits


def test_filter_removes_bin_token_false_positives() -> None:
    hits = [
        {
            "primaryName": "BENEVOLENCE INTERNATIONAL FOUNDATION",
            "submittedName": "БИН 171040021791",
            "isSanction": True,
            "matchStrength": "MEDIUM",
            "matchScore": 84.16,
            "sanctionLists": ["M:2C9"],
        },
        {
            "primaryName": 'ТОО "CORE 24/7"',
            "submittedName": "БИН 171040021791",
            "isSanction": False,
            "matchStrength": "MEDIUM",
            "matchScore": 87.5,
            "sanctionLists": [],
        },
    ]
    filtered = filter_bin_query_false_positive_hits(
        hits,
        screened_name="БИН 171040021791",
        iin="171040021791",
    )
    assert len(filtered) == 1
    assert "CORE" in filtered[0]["primaryName"]
