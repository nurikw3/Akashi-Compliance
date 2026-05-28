from __future__ import annotations

from app.models import db
from app.models.serializers import case_to_api
from app.services.affiliate_tree import cache_snapshot, get_cached_node_report


def _lookup_resolve_from_parent_cache(parent_id: str, iin: str) -> dict | None:
    """Mirror POST /api/lookup cache branch."""
    parent = db.get_case(parent_id)
    if not parent:
        return None
    cached = get_cached_node_report(parent, iin)
    if not cached:
        return None
    open_id = cached.get("openCaseId")
    if open_id:
        row = db.get_case(open_id)
        if row is not None:
            return case_to_api(row)
    return None


def test_lookup_cache_without_open_case_returns_none_then_create_works():
    parent = db.create_case(company_name="Parent Co", iin="171040021792")
    enriched: dict = {"nodeCache": {}}
    cache_snapshot(
        enriched["nodeCache"],
        "240940006279",
        {
            "bin": "240940006279",
            "name": "Affiliate Co",
            "enrichment": {"taxes": {"debt": 0}},
            "assessment": {"riskLevel": "high"},
        },
    )
    db.update_case(parent["id"], enriched_data=enriched)

    assert _lookup_resolve_from_parent_cache(parent["id"], "240940006279") is None

    row = db.create_case(
        company_name="Affiliate Co",
        iin="240940006279",
        parent_case_id=parent["id"],
    )
    assert row["id"]
    assert row.get("parent_case_id") == parent["id"]


def test_lookup_cache_with_open_case_returns_existing_case():
    child = db.create_case(company_name="Existing Affiliate", iin="240940006280")
    parent = db.create_case(company_name="Parent Co", iin="171040021793")
    enriched: dict = {"nodeCache": {}}
    cache_snapshot(
        enriched["nodeCache"],
        "240940006280",
        {
            "bin": "240940006280",
            "name": "Existing Affiliate",
            "enrichment": {},
            "assessment": {"riskLevel": "low"},
        },
    )
    db.update_case(parent["id"], enriched_data=enriched)

    resolved = _lookup_resolve_from_parent_cache(parent["id"], "240940006280")
    assert resolved is not None
    assert resolved["id"] == child["id"]
