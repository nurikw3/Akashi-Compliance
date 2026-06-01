from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)
from app.services.enrichment.base import BaseProvider, CompanyData
from app.services.enrichment.registry import ProviderRegistry, registry
from app.services.enrichment.sources import (
    default_section_sources,
    infer_section_sources_from_data,
    merge_section_sources,
)


class EnrichmentService:
    def __init__(self, provider_registry: ProviderRegistry | None = None) -> None:
        self.registry = provider_registry or registry
        self.last_sources: list[str] = []
        self.last_section_sources: dict[str, str] = default_section_sources()

    async def enrich(self, iin: str) -> tuple[CompanyData, list[str], dict[str, str]]:
        real_providers = self.registry.available()
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

        section_maps: list[dict[str, str]] = []

        if results:
            merged = self.merge([data for _, data in results])
            for provider_name, data in results:
                section_maps.append(
                    data.section_sources
                    if data.section_sources
                    else infer_section_sources_from_data(data, provider_name)
                )
        else:
            logger.warning("No enrichment data for BIN %s — returning empty payload", iin)
            merged = CompanyData(iin=iin, raw={})
            sources = []
            section_maps = [default_section_sources([])]

        self.last_sources = sources
        self.last_section_sources = merge_section_sources(*section_maps) if section_maps else default_section_sources(sources)
        merged.section_sources = self.last_section_sources
        return merged, sources, self.last_section_sources

    async def _safe_check(self, provider: BaseProvider, iin: str) -> CompanyData | None:
        try:
            result = await provider.check(iin)
            if result is None:
                logger.info(
                    "Provider %s returned no data for BIN %s",
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
            return None

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
