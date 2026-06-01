from fastapi import APIRouter

from app.services.enrichment.registry import registry

router = APIRouter(prefix="/api", tags=["providers"])


@router.get("/providers")
def list_providers() -> list[dict[str, object]]:
    return [
        {
            "name": provider.name,
            "available": provider.is_available(),
        }
        for provider in registry.all()
    ]
