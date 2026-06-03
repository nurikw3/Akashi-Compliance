from app.services.ai.full_report_meta import compute_full_report_staleness


def test_stale_when_tree_newer_than_report_snapshot():
    enriched = {
        "fullReport": "# report",
        "fullReportGeneratedAt": "2026-01-01T10:00:00+00:00",
        "fullReportTreeBuiltAt": "2026-01-01T10:00:00+00:00",
        "affiliateTree": {
            "status": "ready",
            "builtAt": "2026-06-01T12:00:00+00:00",
            "nodesCount": 12,
        },
    }
    result = compute_full_report_staleness(enriched)
    assert result["stale"] is True
    assert result["reason"] == "graph_updated"


def test_not_stale_when_tree_matches_snapshot():
    enriched = {
        "fullReport": "# report",
        "fullReportGeneratedAt": "2026-06-01T12:00:00+00:00",
        "fullReportTreeBuiltAt": "2026-06-01T12:00:00+00:00",
        "affiliateTree": {
            "status": "ready",
            "builtAt": "2026-06-01T12:00:00+00:00",
            "nodesCount": 12,
        },
    }
    result = compute_full_report_staleness(enriched)
    assert result["stale"] is False
