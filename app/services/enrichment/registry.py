from __future__ import annotations

from app.services.enrichment.base import BaseProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> BaseProvider:
        return self._providers[name]

    def all(self) -> list[BaseProvider]:
        return list(self._providers.values())

    def available(self) -> list[BaseProvider]:
        return [p for p in self._providers.values() if p.is_available()]


registry = ProviderRegistry()
