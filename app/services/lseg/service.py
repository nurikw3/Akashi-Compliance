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


# ---------------------------------------------------------------------------
# Kazakhstan secondaryFields helpers
# ---------------------------------------------------------------------------


def _extract_dob_from_iin(iin: str) -> str | None:
    """Return YYYY-MM-DD from a 12-digit Kazakhstan IIN, or None if not an individual IIN."""
    if len(iin) != 12 or not iin.isdigit():
        return None
    century_digit = int(iin[6])
    # 7th digit 1-2 → 1800s, 3-4 → 1900s, 5-6 → 2000s; 7-8 → legal entity
    if century_digit in (1, 2):
        prefix = "18"
    elif century_digit in (3, 4):
        prefix = "19"
    elif century_digit in (5, 6):
        prefix = "20"
    else:
        return None
    yyyy, mm, dd = f"{prefix}{iin[0:2]}", iin[2:4], iin[4:6]
    try:
        datetime.strptime(f"{yyyy}-{mm}-{dd}", "%Y-%m-%d")
    except ValueError:
        return None
    return f"{yyyy}-{mm}-{dd}"


def _kz_org_fields(bin_iin: str) -> list[dict]:
    """WC1 secondaryFields for a Kazakhstan organisation.

    SFCT_193 (DOCUMENT_ID_TYPE) is intentionally omitted — WC1 returns 400
    for any DOCUMENT_ID_TYPE value on ORGANISATION entities.
    """
    fields: list[dict] = [{"typeId": "SFCT_6", "value": "KAZ"}]  # REGISTERED_COUNTRY
    if bin_iin and bin_iin.strip():
        fields += [
            {"typeId": "SFCT_191", "value": bin_iin.strip()},  # DOCUMENT_ID = BIN
            {"typeId": "SFCT_192", "value": "KAZ"},            # DOCUMENT_ID_COUNTRY
        ]
    return fields


def _kz_individual_fields(iin: str = "") -> list[dict]:
    """WC1 secondaryFields for a Kazakhstan individual.

    SFCT_193 (DOCUMENT_ID_TYPE) is intentionally omitted — causes 400 on WC1.
    SFCT_2  (DATE_OF_BIRTH)      is intentionally omitted — causes 400 for all
            date formats on this LSEG account (group has 0 secondaryField configs).
            The IIN (SFCT_191) provides sufficient precision filtering alone.
    """
    fields: list[dict] = [
        {"typeId": "SFCT_5", "value": "KAZ"},  # NATIONALITY
        {"typeId": "SFCT_3", "value": "KAZ"},  # COUNTRY_LOCATION
    ]
    if iin and iin.strip() and len(iin) == 12 and iin.isdigit():
        fields += [
            {"typeId": "SFCT_191", "value": iin.strip()},  # DOCUMENT_ID = IIN
            {"typeId": "SFCT_192", "value": "KAZ"},        # DOCUMENT_ID_COUNTRY
        ]
    return fields

# Flips to True after the first 403 MEDIA_CHECK_UNAVAILABLE so we stop paying a
# guaranteed-failing round-trip per organisation when the account lacks the
# Media-Check entitlement. Reset on process restart.
_media_check_unavailable = False


def is_available() -> bool:
    return bool(settings.lseg_client_id and settings.lseg_client_secret and settings.lseg_group_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


_MAX_PROFILE_FETCHES = 5  # max GET /references/records/ calls per entity screening


async def _enrich_hits_with_profiles(hits: list[dict]) -> list[dict]:
    """Fetch full WC1 profiles for material hits to enrich furtherInformation.

    Fetches for:
      - EXACT/STRONG hits that are sanctions → connections + further info
      - Any MEDIUM+ sanctions hit → furtherInformation (причина санкций)
      - Any MEDIUM+ hit with verificationStatus=UNVERIFIED → furtherInformation
        (helps decide if it's a false positive or the real entity)

    Max _MAX_PROFILE_FETCHES calls per screening to keep latency bounded.
    Merges: connections, furtherInformation, sourceReferenceLinks (if inline empty).
    """
    candidates = [
        h for h in hits
        if h.get("referenceId") and (
            # Confirmed strong sanctions hits
            (h.get("isSanction") and h.get("matchStrength", "").upper() in ("STRONG", "EXACT"))
            # MEDIUM sanctions hits — need further info to explain WHY
            or (h.get("isSanction") and h.get("matchStrength", "").upper() == "MEDIUM")
            # Unverified hits — need further info to assess false positive risk
            or h.get("verificationStatus") == "UNVERIFIED"
        )
    ][:_MAX_PROFILE_FETCHES]

    if not candidates:
        return hits

    from app.services.lseg.mapper import (
        _extract_further_information,
        _extract_source_reference_links,
    )

    async def _fetch_profile_enrichment(hit: dict) -> tuple[str, dict]:
        ref_id = hit["referenceId"]
        try:
            profile = await _client.get_profile(ref_id)
            # connections (relationship graph)
            conns = profile.get("connections") or {}
            associates = [
                {
                    "name": a.get("name"),
                    "type": a.get("type"),
                    "isActive": a.get("isActive"),
                    "referenceId": a.get("entityId") or a.get("referenceId"),
                }
                for a in (conns.get("associates") or [])
                if a.get("name")
            ]
            # furtherInformation — WHY they were sanctioned (analyst narrative)
            fi = _extract_further_information(profile.get("furtherInformation"))
            # sourceReferenceLinks — primary source documents (OFAC notice, UN resolution…)
            srl = _extract_source_reference_links(profile.get("sourceReferenceLinks"))
            return ref_id, {
                "connections": associates,
                "furtherInformation": fi or None,       # only overwrite if profile has data
                "sourceReferenceLinks": srl or None,
            }
        except Exception as exc:
            logger.debug("Profile fetch for %s: %s", ref_id, exc)
            return ref_id, {}

    results = await asyncio.gather(*[_fetch_profile_enrichment(h) for h in candidates])
    enrichment_by_ref: dict[str, dict] = dict(results)

    enriched_hits = []
    for h in hits:
        ref_id = h.get("referenceId")
        extra = enrichment_by_ref.get(ref_id) if ref_id else None
        if extra:
            merged = dict(h)
            merged["connections"] = extra.get("connections", [])
            # Only overwrite inline fields if profile returned richer data
            if extra.get("furtherInformation"):
                merged["furtherInformation"] = extra["furtherInformation"]
            if extra.get("sourceReferenceLinks"):
                merged["sourceReferenceLinks"] = extra["sourceReferenceLinks"]
            enriched_hits.append(merged)
        else:
            enriched_hits.append(h)
    return enriched_hits


async def _screen_entity(
    name: str,
    entity_type: str,
    secondary_fields: list[dict] | None = None,
) -> dict[str, Any] | None:
    """Call WC1 for a single entity and return raw screening data.

    Does NOT interact with the cache — callers are responsible for cache
    read/write so this function can be used freely in gather() chains.
    """
    global _media_check_unavailable
    try:
        case_resp = await _client.screen_sync(name, entity_type, secondary_fields)
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
            hits = await _enrich_hits_with_profiles(hits)
        except Exception as exc:
            logger.warning("LSEG get_results failed for %s: %s", name, exc)

        if entity_type == "ORGANISATION" and not _media_check_unavailable:
            try:
                media_resp = await _client.get_media_check(case_id)
                media_articles = _extract_media(media_resp)
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status == 403:
                    _media_check_unavailable = True
                    logger.info(
                        "LSEG media-check entitlement missing (403) — skipping "
                        "media-check for subsequent entities this run"
                    )
                else:
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
    name: str,
    entity_type: str,
    secondary_fields: list[dict] | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Return entity screening data from Redis cache or WC1 API.

    On API success the result is stored in cache for future calls.
    When secondary_fields are provided a separate cache key (`:sf` suffix) is used
    so precision-screened results don't collide with name-only entries.
    """
    cache_key = lseg_key(name, entity_type)
    if secondary_fields:
        cache_key += ":sf"
    cached = await get_cached(cache_key)
    if cached is not None:
        return cached, True

    data = await _screen_entity(name, entity_type, secondary_fields)
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
    director_iin: str = "",
    case_id: str | None = None,
) -> dict[str, Any] | None:
    """Screen company + director via WC1. Returns lseg section dict or None on failure.

    ``iin`` is the company BIN (used as DOCUMENT_ID + REGISTERED_COUNTRY=KAZ).
    ``director_iin`` is the director's personal IIN; when provided it is added
    as DOCUMENT_ID + DATE_OF_BIRTH (extracted from IIN) for the individual search,
    which significantly improves PEP match precision.
    """
    if not is_available():
        return None

    now = datetime.now(timezone.utc).isoformat()
    has_director = bool(director and director.strip() and director != "—")

    org_sf = _kz_org_fields(iin) if iin else None
    ind_sf = _kz_individual_fields(director_iin) if director_iin else _kz_individual_fields()

    company_pair, director_pair = await asyncio.gather(
        _fetch_with_cache_meta(company_name, "ORGANISATION", org_sf),
        _fetch_with_cache_meta(director, "INDIVIDUAL", ind_sf) if has_director else _noop(),  # type: ignore[arg-type]
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
        sf = entity.get("secondary_fields") or None
        cache_key = lseg_key(entity["name"], entity["entity_type"])
        if sf:
            cache_key += ":sf"
        cached = await get_cached(cache_key)
        if cached is not None:
            results[entity["key"]] = cached
            cache_hits += 1
        else:
            uncached.append(entity)

    if not uncached:
        return results

    sem = asyncio.Semaphore(3)

    async def _fetch(entity: dict) -> tuple[str, dict | None]:
        sf = entity.get("secondary_fields") or None
        cache_key = lseg_key(entity["name"], entity["entity_type"])
        if sf:
            cache_key += ":sf"
        async with sem:
            await asyncio.sleep(0.3)  # rate-limit: pause inside the semaphore slot
            data = await _screen_entity(entity["name"], entity["entity_type"], sf)
        if data is not None:
            await set_cached(cache_key, data, LSEG_TTL)
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
    """Drop cached WC1 payloads so the next screen uses fresh API + mapper logic.

    Clears both the plain key and the ``:sf`` (secondary-fields) variant so
    stale mapper data is never served after a code update.
    """
    base = lseg_key(company_name, "ORGANISATION")
    await delete_cached(base)
    await delete_cached(base + ":sf")
    if director and director.strip() and director != "—":
        ind_base = lseg_key(director, "INDIVIDUAL")
        await delete_cached(ind_base)
        await delete_cached(ind_base + ":sf")
    for name, entity_type in extra_names or []:
        if name and name.strip():
            nb = lseg_key(name, entity_type)
            await delete_cached(nb)
            await delete_cached(nb + ":sf")
