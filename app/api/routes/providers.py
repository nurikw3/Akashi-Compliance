from fastapi import APIRouter

from app.services.enrichment.registry import registry
from app.services.enrichment.service import EnrichmentService

router = APIRouter(prefix="/api", tags=["providers"])

_enrichment = EnrichmentService()


@router.get("/providers")
def list_providers() -> list[dict[str, object]]:
    items = []
    for provider in registry.all():
        items.append(
            {
                "name": provider.name,
                "available": provider.is_available(),
                "used_stub": provider.name == "stub" or _enrichment.used_stub,
            }
        )
    if not any(p["name"] == "stub" for p in items):
        items.append({"name": "stub", "available": True, "used_stub": _enrichment.used_stub})
    return items
