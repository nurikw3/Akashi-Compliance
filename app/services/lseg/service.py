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
from app.services.lseg.client import LsegClient
from app.services.lseg.mapper import _extract_hits, _extract_media, build_lseg_section

logger = logging.getLogger(__name__)

_client = LsegClient()


def is_available() -> bool:
    return bool(settings.lseg_client_id and settings.lseg_client_secret and settings.lseg_group_id)


async def screen(
    *,
    company_name: str,
    director: str | None = None,
) -> dict[str, Any] | None:
    """Screen company + director via WC1. Returns lseg section dict or None on failure."""
    if not is_available():
        return None

    now = datetime.now(timezone.utc).isoformat()

    try:
        company_case_resp, director_case_resp = await asyncio.gather(
            _client.screen_sync(company_name, "ORGANISATION"),
            _client.screen_sync(director, "INDIVIDUAL") if director and director.strip() and director != "—" else _noop(),
            return_exceptions=True,
        )
    except Exception as exc:
        logger.error("LSEG screen_sync failed: %s", exc)
        return None

    # If the primary company screen failed — return None so the UI shows "не выполнен"
    if isinstance(company_case_resp, BaseException):
        logger.error("LSEG company screen_sync error: %s", company_case_resp)
        return None

    # Company
    company_case_id = company_case_resp.get("caseSystemId", "") if isinstance(company_case_resp, dict) else ""
    company_hits: list[dict] = []
    if company_case_id:
        try:
            results = await _client.get_results(company_case_id)
            company_hits = _extract_hits(results)
        except Exception as exc:
            logger.warning("LSEG get_results failed for company: %s", exc)

    # Director
    director_hits: list[dict] = []
    if isinstance(director_case_resp, dict):
        director_case_id = director_case_resp.get("caseSystemId", "")
        if director_case_id:
            try:
                results = await _client.get_results(director_case_id)
                director_hits = _extract_hits(results)
            except Exception as exc:
                logger.warning("LSEG get_results failed for director: %s", exc)

    # Media check (company only)
    media_articles: list[dict] = []
    if company_case_id:
        try:
            media_resp = await _client.get_media_check(company_case_id)
            media_articles = _extract_media(media_resp)
        except Exception as exc:
            logger.warning("LSEG media_check failed: %s", exc)

    # WC1 rating (company)
    wc1_rating = ""
    if company_case_id:
        try:
            rating_resp = await _client.get_rating(company_case_id)
            wc1_rating = rating_resp.get("rating", "")
        except Exception as exc:
            logger.debug("LSEG get_rating failed: %s", exc)

    return build_lseg_section(
        company_case_id=company_case_id,
        company_hits=company_hits,
        director_hits=director_hits,
        media_articles=media_articles,
        wc1_rating=wc1_rating,
        screened_at=now,
    )


async def _noop() -> None:
    """Placeholder when director screening is skipped."""
    return None
