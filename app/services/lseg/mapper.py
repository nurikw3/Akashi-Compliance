"""Map LSEG World-Check One v3 API responses to internal dicts."""
from __future__ import annotations

from typing import Any

from app.services.lseg.provider_registry import get_provider_name
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
    """Map raw LSEG source codes to human-readable sanction list names.

    Uses the dynamic provider registry (loaded from /references/providers at
    startup) with a hardcoded fallback for common codes.
    """
    decoded: list[str] = []
    for src in sources:
        label = get_provider_name(src)
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


def _extract_locations(loc_list: list) -> dict[str, Any]:
    """Extract structured location data from result.locations[].

    Returns:
        countries: flat list of ISO codes (for backwards compat)
        countryNames: flat list of country names
        nationalities: list of nationality country names
        locationDetails: structured [{"type": ..., "country": ..., "region": ...}]
    """
    countries: list[str] = []
    country_names: list[str] = []
    nationalities: list[str] = []
    location_details: list[dict] = []

    for loc in loc_list or []:
        country = loc.get("country") or {}
        code = country.get("code", "")
        cname = country.get("name", "")
        loc_type = loc.get("type", "")
        region = next(
            (d.get("value") for d in (loc.get("details") or []) if d.get("type") == "REGION"),
            None,
        )

        location_details.append({
            "type": loc_type,
            "countryCode": code,
            "countryName": cname,
            "region": region,
        })

        if code and code not in countries:
            countries.append(code)
        if cname and cname not in country_names:
            country_names.append(cname)
        if loc_type == "NATIONALITY" and cname and cname not in nationalities:
            nationalities.append(cname)

    return {
        "countries": countries,
        "countryNames": country_names,
        "nationalities": nationalities,
        "locationDetails": location_details,
    }


def _extract_dates(dates_obj: dict | list | None) -> dict[str, str]:
    """Extract entity dates (DOB, incorporation, etc.) as {type: value}.

    WC1 /results returns ``dates`` as a flat list; full profiles use
    ``{"dateDetails": [...]}`` — handle both.
    """
    if isinstance(dates_obj, list):
        return {d.get("type", "?"): d.get("value", "") for d in dates_obj if d.get("value")}
    if not isinstance(dates_obj, dict):
        return {}
    return {
        d.get("type", "?"): d.get("value", "")
        for d in (dates_obj.get("dateDetails") or [])
        if d.get("value")
    }


def _extract_record_dates(rdates: list | None) -> dict[str, str]:
    """Extract WC record lifecycle dates (when added/updated in World-Check)."""
    if not isinstance(rdates, list):
        return {}
    return {d.get("type", "?"): d.get("value", "") for d in rdates if d.get("value")}


def _extract_identifications(ids_obj: dict | list | None) -> list[dict]:
    """Extract sanction/document IDs (OFAC SDN#, UN resolution#, passport, etc.).

    WC1 /results may return ``identifications`` as a flat list; full profiles use
    ``{"identificationDetails": [...]}`` — handle both.
    """
    if isinstance(ids_obj, list):
        details = ids_obj
    elif isinstance(ids_obj, dict):
        details = ids_obj.get("identificationDetails") or []
    else:
        return []
    out = []
    for d in details:
        issuing = d.get("issuingCountry") or {}
        out.append({
            "type": d.get("type"),
            "name": d.get("name"),
            "value": d.get("value"),
            "issuingCountry": issuing.get("name") or issuing.get("code"),
            "issueDate": d.get("issueDate"),
            "expiryDate": d.get("expiryDate"),
        })
    return out


def _extract_further_information(fi_obj: dict | None) -> list[dict]:
    """Extract analyst narrative blocks from furtherInformation."""
    if not isinstance(fi_obj, dict):
        return []
    return [
        {
            "title": d.get("title"),
            "type": d.get("detailType"),
            "text": d.get("text"),
        }
        for d in (fi_obj.get("details") or [])
        if d.get("text")
    ]


def _extract_source_reference_links(srl_obj: dict | None) -> list[dict]:
    """Extract primary source document URLs (official government registers, UN, OFAC, etc.)."""
    if not isinstance(srl_obj, dict):
        return []
    return [
        {"title": lnk.get("title"), "url": lnk.get("url")}
        for lnk in (srl_obj.get("referenceLinks") or srl_obj.get("sourceReferenceLinkDetails") or [])
        if lnk.get("url")
    ]


def _secondary_field_result(result: dict[str, Any]) -> str:
    """Return the highest-confidence secondaryField outcome for a result.

    Priority: NOT_MATCHED > UNKNOWN > MATCHED (worst is most actionable).
    Returns "NONE" when no secondaryFieldResults are present.
    """
    sf_results = result.get("secondaryFieldResults") or []
    outcomes = {r.get("fieldResult", "") for r in sf_results if isinstance(r, dict)}
    if "NOT_MATCHED" in outcomes:
        return "NOT_MATCHED"
    if "MATCHED" in outcomes:
        return "MATCHED"
    if "UNKNOWN" in outcomes:
        return "UNKNOWN"
    return "NONE"


def _extract_secondary_field_results(sf_list: list | None) -> list[dict]:
    """Store raw secondaryFieldResults so UI can answer 'is IIN/BIN confirmed?'"""
    if not isinstance(sf_list, list):
        return []
    return [
        {
            "typeId": r.get("typeId"),
            "submittedValue": r.get("submittedValue"),
            "matchedValue": r.get("matchedValue"),
            "fieldResult": r.get("fieldResult"),  # MATCHED / NOT_MATCHED / UNKNOWN
        }
        for r in sf_list
        if isinstance(r, dict)
    ]


def _extract_matched_terms(terms: list | None) -> list[dict]:
    """Store matchedTerms so UI can answer 'which name/term triggered the match'."""
    if not isinstance(terms, list):
        return []
    return [
        {
            "term": t.get("term"),
            "type": t.get("type"),        # PRIMARY / AKA / NATIVE_AKA / etc.
            "submittedTerm": t.get("submittedTerm"),
        }
        for t in terms
        if isinstance(t, dict)
    ]


def _extract_sanctioning_countries(sanction_lists: list[str]) -> list[str]:
    """Extract the sanctioning jurisdictions from decoded sanction list names.

    E.g. "UK - UKSANC-AF - UK Sanctions List - Asset Freeze" → "United Kingdom"
    Parses the first token of each entry (before first " - ") and maps to a
    full country name when possible.
    """
    _ABBR_MAP = {
        "USA": "United States",
        "US": "United States",
        "UK": "United Kingdom",
        "EU": "European Union",
        "UN": "United Nations",
        "INTERNATIONAL": "International",
        "CANADA": "Canada",
        "AUSTRALIA": "Australia",
        "ISRAEL": "Israel",
        "GERMANY": "Germany",
        "FRANCE": "France",
        "SWITZERLAND": "Switzerland",
        "LUXEMBOURG": "Luxembourg",
        "AUSTRIA": "Austria",
        "SPAIN": "Spain",
        "MALTA": "Malta",
        "MONACO": "Monaco",
        "GUERNSEY": "Guernsey",
        "JERSEY": "Jersey",
        "ISLE OF MAN": "Isle of Man",
        "CAYMAN ISLANDS": "Cayman Islands",
        "SINGAPORE": "Singapore",
        "JAPAN": "Japan",
        "KOREA, SOUTH": "South Korea",
        "TAIWAN": "Taiwan",
        "INDIA": "India",
        "SRI LANKA": "Sri Lanka",
        "NEW ZEALAND": "New Zealand",
        "SOUTH AFRICA": "South Africa",
        "UKRAINE": "Ukraine",
        "UZBEKISTAN": "Uzbekistan",
        "KYRGYZSTAN": "Kyrgyzstan",
        "AZERBAIJAN": "Azerbaijan",
        "TURKIYE": "Türkiye",
        "INDONESIA": "Indonesia",
        "LIECHTENSTEIN": "Liechtenstein",
        "RUSSIAN FEDERATION": "Russia",
    }
    seen: set[str] = set()
    result: list[str] = []
    for entry in sanction_lists:
        # Only process entries with the canonical format "COUNTRY - CODE - Description"
        # Entries without " - " are source categories (e.g. "State Invested Enterprise"),
        # not sanctioning jurisdictions, so skip them.
        if " - " not in entry:
            continue
        prefix = entry.split(" - ")[0].strip().upper()
        if not prefix:
            continue
        label = _ABBR_MAP.get(prefix) or prefix.title()
        if label and label not in seen:
            seen.add(label)
            result.append(label)
    return result


def _compute_verification_status(
    match_strength: str,
    sf_result: str,
    is_sanction: bool,
) -> str:
    """Compute a human-readable verification status for a hit.

    CONFIRMED   — EXACT/STRONG match OR secondary fields confirmed (MATCHED)
    UNVERIFIED  — MEDIUM/WEAK match with UNKNOWN or no secondary field data
    FALSE_POSITIVE — auto-resolved by WC1 as FALSE (excluded before this point)
    """
    strength = (match_strength or "").upper()
    if sf_result == "MATCHED" or strength in ("EXACT", "STRONG"):
        return "CONFIRMED"
    if sf_result == "NOT_MATCHED":
        return "FALSE_POSITIVE"
    return "UNVERIFIED"


def _extract_hits(results_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse /cases/{id}/results into a flat list of enriched hits.

    Each hit includes full WHO/WHAT/WHERE/WHEN fields:
      КТО  — primaryName, aliases, pepStatus, recordType
      ЧТО  — isSanction, sanctionLists, identifications, furtherInformation
      ГДЕ  — locationDetails (typed: CITIZENSHIP, REGISTERED_IN, etc.)
      КОГДА — dates (DOB/incorporation), recordDates (WC publish dates)
      ОТКУДА — sourceReferenceLinks (primary source document URLs)

    Hits auto-resolved as FALSE by WC1 (secondaryField NOT_MATCHED → country
    mismatch) are silently excluded — they are confirmed non-matches.
    """
    hits: list[dict[str, Any]] = []
    for result in results_payload.get("results", []):
        # Exclude hits that WC1 auto-resolved as FALSE (e.g. registered country mismatch)
        resolution = result.get("resolution") or {}
        if resolution.get("resolutionStatusType") == "FALSE":
            continue
        record = result.get("worldCheckRecord") or result.get("matchedRecord") or {}

        categories: list[str] = record.get("categories") or []
        source_categories: list[str] = result.get("sourceCategories") or []
        effective_categories = categories if categories else source_categories

        raw_sources: list[str] = result.get("sources") or []
        is_sanction = bool(_SANCTIONS_CATEGORIES & set(effective_categories)) or _source_codes_indicate_sanction(raw_sources)
        is_pep = bool(_PEP_CATEGORIES & set(effective_categories))
        sanction_lists: list[str] = _decode_sources(raw_sources) if raw_sources else list(dict.fromkeys(source_categories))

        # aliases — all name values from result.names[].details[].value
        aliases: list[str] = []
        for name_entry in result.get("names") or []:
            for detail in name_entry.get("details") or []:
                value = detail.get("value", "")
                if value and value not in aliases:
                    aliases.append(value)

        loc_data = _extract_locations(result.get("locations") or [])
        sf_result_str = _secondary_field_result(result)
        match_strength = result.get("matchStrength", "")

        hits.append(
            {
                # ── match metadata
                "resultId": result.get("resultId", ""),
                "referenceId": result.get("referenceId", ""),
                "primaryName": _primary_name_from_result(result, record),
                "matchStrength": match_strength,
                "matchScore": result.get("matchScore"),
                "submittedName": result.get("submittedTerm", ""),
                "recordType": result.get("recordType", ""),
                # ── verification (key compliance question: «наш контрагент или однофамилец?»)
                "sfResult": sf_result_str,
                "verificationStatus": _compute_verification_status(match_strength, sf_result_str, is_sanction),
                "matchedTerms": _extract_matched_terms(result.get("matchedTerms")),
                "secondaryFieldResults": _extract_secondary_field_results(result.get("secondaryFieldResults")),
                # ── КТО
                "pepStatus": result.get("pepStatus", ""),
                "isSanction": is_sanction,
                "isPep": is_pep,
                "isMaterialMatch": _is_material_watchlist_hit(
                    {
                        "isSanction": is_sanction,
                        "matchScore": result.get("matchScore"),
                        "matchStrength": match_strength,
                        "categories": effective_categories,
                    }
                ),
                "aliases": aliases,
                # ── ЧТО (санкции + страны-инициаторы)
                "sanctionLists": sanction_lists,
                "sanctioningCountries": _extract_sanctioning_countries(sanction_lists),
                "categories": effective_categories,
                "sourceCategories": source_categories,
                "rawSources": raw_sources,
                "identifications": _extract_identifications(result.get("identifications")),
                "furtherInformation": _extract_further_information(result.get("furtherInformation")),
                # ── ГДЕ
                "countries": loc_data["countries"],
                "countryNames": loc_data["countryNames"],
                "nationalities": loc_data["nationalities"],
                "locationDetails": loc_data["locationDetails"],
                # ── КОГДА
                "dates": _extract_dates(result.get("dates")),
                "recordDates": _extract_record_dates(result.get("recordDates")),
                # ── ОТКУДА (первоисточники)
                "sourceReferenceLinks": _extract_source_reference_links(result.get("sourceReferenceLinks")),
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
