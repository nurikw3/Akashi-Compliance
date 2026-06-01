"""Map LSEG World-Check One v3 API responses to internal dicts."""
from __future__ import annotations

from typing import Any


_SANCTIONS_CATEGORIES = {"SAN", "SIP", "REG-SAN"}
_PEP_CATEGORIES = {"PEP", "PEP-CLASS1", "PEP-CLASS2", "PEP-CLASS3", "PEP-CLASS4", "RCA"}
_ADVERSE_RISK_MAP = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _extract_hits(results_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse /cases/{id}/results response into a flat list of hits."""
    hits: list[dict[str, Any]] = []
    for result in results_payload.get("results", []):
        record = result.get("worldCheckRecord") or result.get("matchedRecord") or {}
        categories: list[str] = record.get("categories") or []
        sources: list[str] = [
            s.get("name", "")
            for s in (record.get("sources") or [])
            if s.get("name")
        ]
        hits.append(
            {
                "resultId": result.get("resultId", ""),
                "primaryName": record.get("primaryName") or result.get("matchedName", ""),
                "categories": categories,
                "sources": sources,
                "isSanction": bool(_SANCTIONS_CATEGORIES & set(categories)),
                "isPep": bool(_PEP_CATEGORIES & set(categories)),
            }
        )
    return hits


def _extract_media(media_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse /media-check/results response into a compact list of articles."""
    articles: list[dict[str, Any]] = []
    for article in media_payload.get("articles") or []:
        articles.append(
            {
                "articleId": article.get("articleId", ""),
                "headline": article.get("headline") or article.get("title", ""),
                "publicationDate": article.get("publicationDate", ""),
                "url": article.get("url", ""),
                "risk": article.get("risk", ""),
                "categories": article.get("categories") or [],
            }
        )
    return articles


def build_lseg_section(
    *,
    company_case_id: str,
    company_hits: list[dict[str, Any]],
    director_hits: list[dict[str, Any]],
    media_articles: list[dict[str, Any]],
    wc1_rating: str,
    screened_at: str,
) -> dict[str, Any]:
    """Assemble the enriched_data.lseg section stored in the DB."""
    sanction_hits = [h for h in company_hits if h["isSanction"]]
    pep_hits = [h for h in director_hits if h["isPep"]]
    negative_media = [a for a in media_articles if a.get("risk") in ("HIGH", "MEDIUM")]

    matched_lists: list[str] = []
    for h in sanction_hits:
        matched_lists.extend(h["sources"])
    matched_lists = list(dict.fromkeys(matched_lists))

    return {
        "caseSystemId": company_case_id,
        "screenedAt": screened_at,
        "wc1Rating": wc1_rating,
        "sanctions": {
            "isOnList": bool(sanction_hits),
            "matchedLists": matched_lists,
            "hits": sanction_hits,
        },
        "pep": {
            "isHit": bool(pep_hits),
            "individuals": pep_hits,
        },
        "adverseMedia": {
            "articles": media_articles,
            "negativeCount": len(negative_media),
        },
    }
