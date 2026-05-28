from __future__ import annotations

from app.services.affiliate_tree import cache_snapshot, get_cached_node_report


def test_get_cached_node_report_from_node_cache():
    row = {
        "id": "case-1",
        "company_name": "Root",
        "iin": "171040021791",
        "risk_level": "low",
        "conclusion": "ok",
        "enriched_data": {
            "enrichment": {"companyInfo": {"fullName": "Root"}},
            "assessment": {"riskLevel": "low"},
            "nodeCache": {
                "200940900061": {
                    "bin": "200940900061",
                    "name": "Child",
                    "enrichment": {"taxes": {"debt": 0}},
                    "assessment": {"riskLevel": "medium"},
                }
            },
        },
    }
    report = get_cached_node_report(row, "200940900061")
    assert report is not None
    assert report["source"] == "cache"
    assert report["name"] == "Child"
    assert report.get("openCaseId") is None

    main = get_cached_node_report(row, "171040021791")
    assert main is not None
    assert main["source"] == "main"
