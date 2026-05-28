from __future__ import annotations

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)
from app.services.enrichment.base import BaseProvider, CompanyData
from app.services.enrichment.providers.stub import StubProvider
from app.services.enrichment.registry import ProviderRegistry, registry
from app.services.enrichment.sources import (
    default_section_sources,
    infer_section_sources_from_data,
    merge_section_sources,
)


class EnrichmentService:
    def __init__(self, provider_registry: ProviderRegistry | None = None) -> None:
        self.registry = provider_registry or registry
        self._stub = StubProvider()
        self.last_sources: list[str] = []
        self.last_section_sources: dict[str, str] = default_section_sources()
        self.used_stub = False

    async def enrich(self, iin: str) -> tuple[CompanyData, list[str], dict[str, str]]:
        real_providers = [
            p for p in self.registry.available() if p.name != "stub"
        ]
        results: list[tuple[str, CompanyData]] = []

        if real_providers:
            checks = await asyncio.gather(
                *[self._safe_check(provider, iin) for provider in real_providers],
                return_exceptions=True,
            )
            for provider, result in zip(real_providers, checks):
                if isinstance(result, CompanyData):
                    results.append((provider.name, result))

        sources = [name for name, _ in results]
        self.used_stub = False

        section_maps: list[dict[str, str]] = []

        if results:
            merged = self.merge([data for _, data in results])
            for provider_name, data in results:
                section_maps.append(
                    data.section_sources
                    if data.section_sources
                    else infer_section_sources_from_data(data, provider_name)
                )
            # Do not merge stub CompanyData — avoids fake courts/affiliates in UI.
        else:
            merged = await self._stub.check(iin)
            sources = ["stub"]
            section_maps = [infer_section_sources_from_data(merged, "stub")]
            self.used_stub = True

        self.last_sources = sources
        self.last_section_sources = merge_section_sources(*section_maps) if section_maps else default_section_sources(sources)
        merged.section_sources = self.last_section_sources
        return merged, sources, self.last_section_sources

    async def _safe_check(self, provider: BaseProvider, iin: str) -> CompanyData | None:
        try:
            result = await provider.check(iin)
            if result is None and provider.name != "stub":
                logger.info(
                    "Provider %s returned no data for BIN %s; will use stub fallback",
                    provider.name,
                    iin,
                )
            return result
        except Exception as exc:
            logger.info(
                "Provider %s check failed for BIN %s: %s",
                provider.name,
                iin,
                exc,
            )
            if settings.use_stub_on_api_failure:
                return None
            raise

    def merge(self, results: list[CompanyData]) -> CompanyData:
        if not results:
            raise ValueError("No enrichment results to merge")
        merged = results[0].model_copy(deep=True)
        for result in results[1:]:
            for field in CompanyData.model_fields:
                current = getattr(merged, field)
                incoming = getattr(result, field)
                if field == "raw":
                    merged.raw = {**result.raw, **merged.raw}
                elif field in ("founders", "related_companies", "court_cases_years"):
                    if incoming and not current:
                        setattr(merged, field, incoming)
                    elif incoming and current:
                        setattr(merged, field, current + incoming)
                elif field == "court_totals":
                    if incoming and not current:
                        setattr(merged, field, incoming)
                elif field == "section_sources":
                    if incoming:
                        merged.section_sources = {**incoming, **merged.section_sources}
                elif current in (None, "", [], {}) and incoming not in (
                    None,
                    "",
                    [],
                    {},
                ):
                    setattr(merged, field, incoming)
        return merged
