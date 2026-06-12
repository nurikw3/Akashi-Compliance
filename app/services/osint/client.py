"""Pluggable web-search client for OSINT enrichment.

The orchestration layer only depends on the :class:`SearchClient` protocol, so a
provider can be swapped via ``OSINT_SEARCH_PROVIDER`` without touching the
service. Tavily is the default and is called over plain ``httpx`` — matching the
codebase convention of hitting REST APIs directly rather than adding an SDK
dependency (see ``adata/client.py`` / ``lseg/client.py``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TAVILY_DEFAULT_URL = "https://api.tavily.com/search"


def domain_of(url: str) -> str:
    """Registrable host of a URL: ``https://www.kursiv.media/x`` → ``kursiv.media``."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    published_date: str | None = None
    source_name: str = ""

    def __post_init__(self) -> None:
        if not self.source_name:
            self.source_name = domain_of(self.url)


class SearchClient(Protocol):
    async def search(
        self, query: str, *, max_results: int, lang: str | None = None
    ) -> list[SearchHit]:
        ...


class TavilyClient:
    """Tavily REST search via ``httpx`` (no SDK dependency)."""

    name = "tavily"

    def __init__(self) -> None:
        self._api_key = settings.osint_search_api_key
        self._base_url = settings.osint_search_base_url or _TAVILY_DEFAULT_URL
        self._timeout = settings.osint_timeout_seconds

    async def search(
        self, query: str, *, max_results: int, lang: str | None = None
    ) -> list[SearchHit]:
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._base_url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        hits: list[SearchHit] = []
        for item in data.get("results") or []:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            hits.append(
                SearchHit(
                    title=str(item.get("title") or "").strip(),
                    url=url,
                    snippet=str(item.get("content") or "").strip(),
                    published_date=item.get("published_date"),
                )
            )
        return hits


def get_search_client() -> SearchClient | None:
    """Return the configured search client, or ``None`` when OSINT search is off.

    Dispatches on ``OSINT_SEARCH_PROVIDER``. Only Tavily is wired today; Exa,
    Perplexity Sonar, Serper and Brave can be added here behind the same
    protocol. Unknown providers fall back to Tavily with a warning.
    """
    if not settings.osint_search_api_key:
        return None
    provider = (settings.osint_search_provider or "tavily").strip().lower()
    if provider != "tavily":
        logger.warning(
            "Unknown OSINT_SEARCH_PROVIDER=%r; falling back to Tavily", provider
        )
    return TavilyClient()
