from __future__ import annotations

from app.services.enrichment.base import BaseProvider, CompanyData


class KompraProvider(BaseProvider):
    """Placeholder for future Kompra integration."""

    name = "kompra"

    def is_available(self) -> bool:
        return False

    async def check(self, iin: str, company_name: str = "") -> CompanyData | None:
        raise NotImplementedError("Kompra provider is not implemented in MVP.")
