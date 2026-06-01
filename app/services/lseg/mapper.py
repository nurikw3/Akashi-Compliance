"""Map LSEG World-Check One v3 API responses to internal dicts."""
from __future__ import annotations

from typing import Any

from app.services.lseg.screening import filter_bin_query_false_positive_hits


_SANCTIONS_CATEGORIES = {"SAN", "SIP", "REG-SAN"}
_PEP_CATEGORIES = {"PEP", "PEP-CLASS1", "PEP-CLASS2", "PEP-CLASS3", "PEP-CLASS4", "RCA"}
_ADVERSE_RISK_MAP = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

# Source code fragments that indicate a sanction list entry (even if sourceCategories is generic)
_SANCTION_SOURCE_KEYWORDS = {
    "RSSRE", "INSAE", "RUPTRE", "OFAC", "UKHMT", "BIS", "SIE",
    "SDN", "SANCTIONS", "SANCTIONED",
}

# WC1 category labels (human-readable) that warrant escalation when match is strong
_HIGH_RISK_CATEGORY_FRAGMENTS = (
    "REGULATORY ENFORCEMENT",
    "SPECIAL INTEREST",
    "SANCTION",
)


def _source_codes_indicate_sanction(sources: list[str]) -> bool:
    """Return True if any source code contains a known sanctions indicator."""
    for src in sources:
        upper = src.upper()
        if any(kw in upper for kw in _SANCTION_SOURCE_KEYWORDS):
            return True
    return False


def _decode_sources(sources: list[str]) -> list[str]:
    """Map raw LSEG source codes to human-readable sanction list names."""
    _MAP = {
        "RSSRE-WC": "Russia Specially Designated Related Entities",
        "RSSRE-50-WC": "Russia Specially Designated Related Entities (50% Rule)",
        "INSAE-50-OFAC-WC": "OFAC (US Treasury) – 50% Rule",
        "INSAE-50-UKHMT-WC": "UK HM Treasury – 50% Rule",
        "INSAE-50-WC": "Interdicted & Sanctioned Associated Entities (50% Rule)",
        "INSAE-WC": "Interdicted & Sanctioned Associated Entities",
        "RUPTRE-WC": "Russia Restrictive Measures (EU)",
        "BIS-WC": "US Bureau of Industry and Security (Export Controls)",
        "SIE": "Special Interest Entities",
    }
    decoded: list[str] = []
    for src in sources:
        # strip prefix "b_trwc_" or "b_trwc_M:"
        key = src.replace("b_trwc_", "").replace("b_tr_", "")
        label = _MAP.get(key, key)
        if label not in decoded:
            decoded.append(label)
    return decoded


def _primary_name_from_result(result: dict[str, Any], record: dict[str, Any]) -> str:
    """Resolve display name from WC1 result (primaryName is often absent on v3 payloads)."""
    name = record.get("primaryName") or result.get("matchedName")
    if name:
        return str(name)
    for name_entry in result.get("names") or []:
        if name_entry.get("type") == "PRIMARY":
            for detail in name_entry.get("details") or []:
                value = detail.get("value", "")
                if value:
                    return str(value)
    for name_entry in result.get("names") or []:
        for detail in name_entry.get("details") or []:
            value = detail.get("value", "")
            if value:
                return str(value)
    return ""


def _is_material_watchlist_hit(hit: dict[str, Any]) -> bool:
    """Strong WC1 watchlist match that must surface in UI/scoring (not only formal SAN rows)."""
    if hit.get("isSanction"):
        return True
    try:
        score = float(hit.get("matchScore") or 0)
    except (TypeError, ValueError):
        score = 0.0
    strength = (hit.get("matchStrength") or "").upper()
    if strength not in ("STRONG", "EXACT") or score < 80:
        return False
    cats_text = " ".join(hit.get("categories") or []).upper()
    return any(frag in cats_text for frag in _HIGH_RISK_CATEGORY_FRAGMENTS)


def _extract_hits(results_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse /cases/{id}/results or screen_sync response into a flat list of enriched hits."""
    hits: list[dict[str, Any]] = []
    for result in results_payload.get("results", []):
        record = result.get("worldCheckRecord") or result.get("matchedRecord") or {}

        # Categories: prefer worldCheckRecord.categories, fall back to sourceCategories
        categories: list[str] = record.get("categories") or []
        source_categories: list[str] = result.get("sourceCategories") or []
        effective_categories = categories if categories else source_categories

        # Raw source codes (e.g. "b_trwc_INSAE-50-OFAC-WC")
        raw_sources: list[str] = result.get("sources") or []

        # isSanction: check effective_categories first; fall back to raw source codes
        is_sanction = bool(_SANCTIONS_CATEGORIES & set(effective_categories)) or _source_codes_indicate_sanction(raw_sources)
        is_pep = bool(_PEP_CATEGORIES & set(effective_categories))

        # sanctionLists — human-readable list names decoded from raw sources
        sanction_lists: list[str] = _decode_sources(raw_sources) if raw_sources else list(dict.fromkeys(source_categories))

        # locations: split into country codes/names and nationalities
        countries: list[str] = []
        country_names: list[str] = []
        nationalities: list[str] = []
        for loc in result.get("locations") or []:
            country = loc.get("country") or {}
            code = country.get("code", "")
            name = country.get("name", "")
            loc_type = loc.get("type", "")
            if loc_type in ("LOCATION", "NATIONALITY") and code:
                if code not in countries:
                    countries.append(code)
                if name and name not in country_names:
                    country_names.append(name)
            if loc_type == "NATIONALITY" and name and name not in nationalities:
                nationalities.append(name)

        # aliases — all name values from result.names[].details[].value
        aliases: list[str] = []
        for name_entry in result.get("names") or []:
            for detail in name_entry.get("details") or []:
                value = detail.get("value", "")
                if value and value not in aliases:
                    aliases.append(value)

        hits.append(
            {
                "resultId": result.get("resultId", ""),
                "primaryName": _primary_name_from_result(result, record),
                "matchStrength": result.get("matchStrength", ""),
                "matchScore": result.get("matchScore"),
                "submittedName": result.get("submittedTerm", ""),
                "isSanction": is_sanction,
                "isPep": is_pep,
                "isMaterialMatch": _is_material_watchlist_hit(
                    {
                        "isSanction": is_sanction,
                        "matchScore": result.get("matchScore"),
                        "matchStrength": result.get("matchStrength", ""),
                        "categories": effective_categories,
                    }
                ),
                "sanctionLists": sanction_lists,
                "countries": countries,
                "countryNames": country_names,
                "nationalities": nationalities,
                "categories": effective_categories,
                "aliases": aliases,
                "sourceCategories": source_categories,
                "rawSources": raw_sources,
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


def build_lseg_extended_entities(
    targets: list[dict[str, Any]],
    batch: dict[str, dict[str, Any] | None],
) -> dict[str, dict[str, Any]]:
    """Map screen_batch raw results to the shape expected by the frontend."""
    key_to_target = {t["key"]: t for t in targets}
    out: dict[str, dict[str, Any]] = {}
    for key, data in batch.items():
        target = key_to_target.get(key, {})
        base = {
            "name": target.get("name") or key,
            "entityType": target.get("entity_type", "ORGANISATION"),
            "role": target.get("role"),
            "country": target.get("country"),
        }
        if not isinstance(data, dict):
            out[key] = {
                **base,
                "isOnSanctionList": False,
                "sanctionLists": [],
                "hits": [],
            }
            continue
        hits: list[dict[str, Any]] = data.get("hits") or []
        flagged = [h for h in hits if h.get("isSanction") or h.get("isMaterialMatch")]
        lists: list[str] = []
        for h in flagged:
            lists.extend(h.get("sanctionLists") or [])
        out[key] = {
            **base,
            "isOnSanctionList": bool(flagged),
            "sanctionLists": list(dict.fromkeys(lists)),
            "hits": hits,
        }
    # Ensure every requested target has an entry (even if batch omitted a key).
    for target in targets:
        key = target["key"]
        if key not in out:
            out[key] = {
                "name": target.get("name") or key,
                "entityType": target.get("entity_type", "ORGANISATION"),
                "role": target.get("role"),
                "country": target.get("country"),
                "isOnSanctionList": False,
                "sanctionLists": [],
                "hits": [],
            }
    return out


def build_lseg_section(
    *,
    company_case_id: str,
    company_hits: list[dict[str, Any]],
    director_hits: list[dict[str, Any]],
    media_articles: list[dict[str, Any]],
    wc1_rating: str,
    screened_at: str,
    screened_name: str = "",
    screened_iin: str = "",
) -> dict[str, Any]:
    """Assemble the enriched_data.lseg section stored in the DB."""
    company_hits = filter_bin_query_false_positive_hits(
        company_hits,
        screened_name=screened_name,
        iin=screened_iin,
    )
    formal_sanction_hits = [h for h in company_hits if h.get("isSanction")]
    listing_hits = [
        h for h in company_hits
        if h.get("isSanction") or h.get("isMaterialMatch") or _is_material_watchlist_hit(h)
    ]
    pep_hits = [h for h in director_hits if h["isPep"]]
    negative_media = [a for a in media_articles if a.get("risk") in ("HIGH", "MEDIUM")]

    matched_lists: list[str] = []
    for h in listing_hits:
        matched_lists.extend(h.get("sanctionLists") or h.get("sources") or [])
    matched_lists = list(dict.fromkeys(matched_lists))

    return {
        "caseSystemId": company_case_id,
        "screenedAt": screened_at,
        "wc1Rating": wc1_rating,
        "screenedName": screened_name,
        "screenedIin": screened_iin,
        "sanctions": {
            "isOnList": bool(formal_sanction_hits),
            "hasWatchlistHits": bool(listing_hits),
            "isFormalSanction": bool(formal_sanction_hits),
            "matchedLists": matched_lists,
            "hits": company_hits,
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
