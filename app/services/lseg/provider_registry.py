"""WC1 provider registry — dynamic lookup for /references/providers.

Loaded once at startup (API lifespan + worker startup) and cached in Redis
for 24 h. Falls back gracefully: if the registry hasn't loaded yet, returns
the raw source code unchanged so existing data is never lost.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_CACHE_KEY = "lseg:providers:v1"
_CACHE_TTL = 86400  # 24 h

# In-memory lookup: normalised source code → human-readable name.
# Populated by load_provider_registry(); read synchronously by get_provider_name().
_registry: dict[str, str] = {}

# Hardcoded fallback for the most common codes (used when registry not yet loaded)
_FALLBACK: dict[str, str] = {
    "RSSRE-WC":          "Russia Specially Designated Related Entities",
    "RSSRE-50-WC":       "Russia Specially Designated Related Entities (50% Rule)",
    "INSAE-50-OFAC-WC":  "OFAC (US Treasury) – 50% Rule",
    "INSAE-50-UKHMT-WC": "UK HM Treasury – 50% Rule",
    "INSAE-50-WC":       "Interdicted & Sanctioned Associated Entities (50% Rule)",
    "INSAE-WC":          "Interdicted & Sanctioned Associated Entities",
    "RUPTRE-WC":         "Russia Restrictive Measures (EU)",
    "BIS-WC":            "US Bureau of Industry and Security (Export Controls)",
    "SIE":               "Special Interest Entities",
}


def _normalize_code(raw: str) -> str:
    """Strip LSEG namespace prefixes so the key matches the API identifier."""
    return raw.replace("b_trwc_", "").replace("b_tr_", "").strip()


def _build_index(providers: list[dict[str, Any]]) -> dict[str, str]:
    """Build normalised code → name mapping from a /references/providers response.

    WC1 v3 returns a list of provider objects, each with a nested ``sources``
    array.  Each source entry has ``identifier`` (full code, e.g.
    ``b_trwc_UKSANC``) and ``name`` (human-readable label).
    """
    index: dict[str, str] = {}
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        for src in provider.get("sources") or []:
            if not isinstance(src, dict):
                continue
            name: str = (src.get("name") or "").strip()
            if not name:
                continue
            for key_field in ("identifier", "abbreviation"):
                code = (src.get(key_field) or "").strip()
                if code:
                    index[_normalize_code(code)] = name
    return index


async def load_provider_registry() -> None:
    """Fetch /references/providers, populate in-memory registry, cache in Redis.

    Called at FastAPI lifespan startup and worker startup.  Safe to call
    multiple times — a warm Redis cache means no API call is made.
    """
    global _registry

    if not settings.lseg_client_id or not settings.lseg_client_secret:
        logger.debug("LSEG not configured — skipping provider registry load")
        return

    # Try Redis cache first
    _MIN_REGISTRY_SIZE = 100  # fewer entries = stale/fallback-only cache

    try:
        from app.services.cache import get_cached, set_cached
        cached = await get_cached(_CACHE_KEY)
        if isinstance(cached, dict) and len(cached) >= _MIN_REGISTRY_SIZE:
            _registry = cached
            logger.info("LSEG provider registry loaded from Redis (%d entries)", len(_registry))
            return
        if isinstance(cached, dict) and cached:
            logger.info(
                "LSEG provider registry cache stale (%d entries < %d) — refreshing from API",
                len(cached), _MIN_REGISTRY_SIZE,
            )
    except Exception as exc:
        logger.debug("Redis unavailable for provider registry: %s", exc)

    # Fetch from API
    try:
        from app.services.lseg.client import LsegClient
        client = LsegClient()
        base = "https://api.risk.lseg.com/screening/v3"
        raw = await client._request("GET", f"{base}/references/providers")
    except Exception as exc:
        logger.warning("Failed to fetch LSEG provider registry: %s — using fallback", exc)
        _registry = dict(_FALLBACK)
        return

    # The API may return a top-level list or a dict with a list inside
    if isinstance(raw, list):
        providers = raw
    elif isinstance(raw, dict):
        # Common key names seen in LSEG v3 docs
        for key in ("providerSources", "providers", "content", "data", "results"):
            if isinstance(raw.get(key), list):
                providers = raw[key]
                break
        else:
            providers = []
    else:
        providers = []

    index = _build_index(providers)
    if not index:
        logger.warning("LSEG provider registry returned empty index — using fallback")
        _registry = dict(_FALLBACK)
        return

    # Merge fallback so well-known codes always have nice labels
    _registry = {**_FALLBACK, **index}
    logger.info("LSEG provider registry loaded from API (%d entries)", len(_registry))

    try:
        from app.services.cache import set_cached
        await set_cached(_CACHE_KEY, _registry, _CACHE_TTL)
    except Exception as exc:
        logger.debug("Could not cache provider registry in Redis: %s", exc)


def get_provider_name(raw_code: str) -> str:
    """Return the human-readable name for a WC1 source code.

    Strips LSEG namespace prefixes, looks up in the loaded registry, then
    falls back to the hardcoded map, then returns the normalised code as-is.
    """
    key = _normalize_code(raw_code)
    return _registry.get(key) or _FALLBACK.get(key) or key
