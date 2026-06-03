"""High-level LSEG World-Check One screening service.

Screens a company (ORGANISATION) and optionally its director (INDIVIDUAL)
and returns the enriched_data.lseg section ready to be stored.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.services.cache import LSEG_TTL, delete_cached, get_cached, lseg_key, set_cached
from app.services.lseg.client import LsegClient
from app.services.lseg.mapper import _extract_hits, _extract_media, build_lseg_section
from app.services.verification_log import append_case_event

logger = logging.getLogger(__name__)

_client = LsegClient()


def is_available() -> bool:
    return bool(settings.lseg_client_id and settings.lseg_client_secret and settings.lseg_group_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _screen_entity(name: str, entity_type: str) -> dict[str, Any] | None:
    """Call WC1 for a single entity and return raw screening data.

    Does NOT interact with the cache — callers are responsible for cache
    read/write so this function can be used freely in gather() chains.
    """
    try:
        case_resp = await _client.screen_sync(name, entity_type)
    except Exception as exc:
        logger.error("LSEG screen_sync failed for %s (%s): %s", name, entity_type, exc)
        return None

    if not isinstance(case_resp, dict):
        return None

    case_id: str = case_resp.get("caseSystemId", "")
    hits: list[dict] = []
    media_articles: list[dict] = []
    wc1_rating = ""

    if case_id:
        try:
            results = await _client.get_results(case_id)
            hits = _extract_hits(results)
        except Exception as exc:
            logger.warning("LSEG get_results failed for %s: %s", name, exc)

        if entity_type == "ORGANISATION":
            try:
                media_resp = await _client.get_media_check(case_id)
                media_articles = _extract_media(media_resp)
            except Exception as exc:
                logger.warning("LSEG media_check failed for %s: %s", name, exc)

            try:
                rating_resp = await _client.get_rating(case_id)
                wc1_rating = rating_resp.get("rating", "")
            except Exception as exc:
                logger.debug("LSEG get_rating failed for %s: %s", name, exc)

    return {
        "case_id": case_id,
        "hits": hits,
        "media_articles": media_articles,
        "wc1_rating": wc1_rating,
    }


async def _fetch_with_cache_meta(
    name: str, entity_type: str
) -> tuple[dict[str, Any] | None, bool]:
    """Return entity screening data from Redis cache or WC1 API.

    On API success the result is stored in cache for future calls.
    """
    cache_key = lseg_key(name, entity_type)
    cached = await get_cached(cache_key)
    if cached is not None:
        return cached, True

    data = await _screen_entity(name, entity_type)
    if data is not None:
        await set_cached(cache_key, data, LSEG_TTL)
    return data, False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def screen(
    *,
    company_name: str,
    director: str | None = None,
    iin: str = "",
    case_id: str | None = None,
) -> dict[str, Any] | None:
    """Screen company + director via WC1. Returns lseg section dict or None on failure."""
    if not is_available():
        return None

    now = datetime.now(timezone.utc).isoformat()
    has_director = bool(director and director.strip() and director != "—")

    company_pair, director_pair = await asyncio.gather(
        _fetch_with_cache_meta(company_name, "ORGANISATION"),
        _fetch_with_cache_meta(director, "INDIVIDUAL") if has_director else _noop(),  # type: ignore[arg-type]
    )

    company_data, company_cached = company_pair if isinstance(company_pair, tuple) else (None, False)
    director_data, director_cached = (
        director_pair if isinstance(director_pair, tuple) else (None, False)
    )

    if not isinstance(company_data, dict):
        logger.error("LSEG company screening failed for %s", company_name)
        if case_id:
            append_case_event(
                case_id,
                provider="LSEG",
                action="screen",
                subject={"type": "BIN", "value": iin, "name": company_name},
                request={"endpoint": "WC1 screen_sync + results/media/rating"},
                outcome={"status": "error", "cached": False, "message": "company_screen_failed"},
            )
        return None

    section = build_lseg_section(
        company_case_id=company_data["case_id"],
        company_hits=company_data["hits"],
        director_hits=director_data["hits"] if isinstance(director_data, dict) else [],
        media_articles=company_data.get("media_articles", []),
        wc1_rating=company_data.get("wc1_rating", ""),
        screened_at=now,
        screened_name=company_name,
        screened_iin=iin,
    )
    if case_id:
        append_case_event(
            case_id,
            provider="LSEG",
            action="screen",
            subject={"type": "BIN", "value": iin, "name": company_name},
            request={"endpoint": "WC1 screen_sync + results/media/rating"},
            outcome={
                "status": "ok",
                "cached": bool(company_cached and (director_cached if has_director else True)),
                "counts": {
                    "companyHits": len(company_data.get("hits") or []),
                    "directorHits": len((director_data or {}).get("hits") or []) if isinstance(director_data, dict) else 0,
                    "mediaArticles": len(company_data.get("media_articles") or []),
                },
                "meta": {
                    "companyCached": company_cached,
                    "directorCached": director_cached if has_director else None,
                },
            },
        )
    return section


async def screen_batch(
    entities: list[dict],
    *,
    case_id: str | None = None,
) -> dict[str, dict | None]:
    """Screen multiple entities in parallel with Redis caching and rate limiting.

    Args:
        entities: List of dicts with keys:
            - ``name`` (str): entity display name
            - ``entity_type`` (str): ``"ORGANISATION"`` or ``"INDIVIDUAL"``
            - ``key`` (str): unique caller-defined identifier used as the
              result dict key (e.g. BIN or a person identifier)

    Returns:
        ``{key: entity_data_dict_or_None}`` for every input entity.
    """
    if not is_available():
        return {e["key"]: None for e in entities}

    # Split entities into cache-hits and cache-misses in one pass.
    results: dict[str, dict | None] = {}
    uncached: list[dict] = []

    cache_hits = 0
    for entity in entities:
        cached = await get_cached(lseg_key(entity["name"], entity["entity_type"]))
        if cached is not None:
            results[entity["key"]] = cached
            cache_hits += 1
        else:
            uncached.append(entity)

    if not uncached:
        return results

    sem = asyncio.Semaphore(3)

    async def _fetch(entity: dict) -> tuple[str, dict | None]:
        async with sem:
            await asyncio.sleep(0.3)  # rate-limit: pause inside the semaphore slot
            data = await _screen_entity(entity["name"], entity["entity_type"])
        if data is not None:
            await set_cached(
                lseg_key(entity["name"], entity["entity_type"]),
                data,
                LSEG_TTL,
            )
        return entity["key"], data

    fetched: list[tuple[str, dict | None]] = await asyncio.gather(
        *[_fetch(e) for e in uncached]
    )
    results.update(fetched)
    if case_id:
        append_case_event(
            case_id,
            provider="LSEG",
            action="screen_batch",
            request={"endpoint": "WC1 batch (parallel per-entity)"},
            outcome={
                "status": "ok",
                "cached": cache_hits == len(entities),
                "counts": {
                    "targets": len(entities),
                    "cachedHits": cache_hits,
                    "freshCalls": len(uncached),
                },
            },
        )
    return results


async def _noop() -> None:
    """Placeholder when director screening is skipped."""
    return None


async def invalidate_screening_cache(
    company_name: str,
    director: str | None = None,
    *,
    extra_names: list[tuple[str, str]] | None = None,
) -> None:
    """Drop cached WC1 payloads so the next screen uses fresh API + mapper logic."""
    await delete_cached(lseg_key(company_name, "ORGANISATION"))
    if director and director.strip() and director != "—":
        await delete_cached(lseg_key(director, "INDIVIDUAL"))
    for name, entity_type in extra_names or []:
        if name and name.strip():
            await delete_cached(lseg_key(name, entity_type))
