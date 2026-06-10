from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.models import db
from app.services.adata.client import (
    deep_find,
    fetch_beneficiary,
    fetch_company_court_cases,
    fetch_company_info,
    fetch_director_iin,
    fetch_individual_court_cases,
    fetch_individual_info,
    fetch_non_resident_affiliations,
    fetch_relation_extended,
    fetch_trustworthy_plus,
)
from app.services.adata.info_mapper import map_info_data
from app.services.affiliate_tree import _empty_tree_meta
from app.services.enrichment.base import CompanyData
from app.services.enrichment.mapper import (
    build_assessment,
    company_data_to_enrichment,
)
from app.services.enrichment.service import EnrichmentService
import app.services.lseg.service as lseg_service
from app.services.lseg.mapper import build_lseg_extended_entities
from app.services.ai.court_analyzer import analyze_court_cases
from app.services.verification_log import add_event_to_enriched

from app.services.company_display import resolve_company_display_name

logger = logging.getLogger(__name__)


def _resolved_company_name(company_name: str, iin: str, enrichment: dict[str, Any]) -> str:
    return resolve_company_display_name(company_name, iin, enrichment)

_KZ_BIN_RE = re.compile(r"^\d{12}$")
_DIRECTOR_IIN_KEYS = frozenset(
    {
        "director_iin",
        "head_iin",
        "manager_iin",
        "ceo_iin",
        "directoriin",
        "headiin",
        "head_biin",
        "head_biin_formatted",
        "head_bin",
        "head_bin_formatted",
    }
)
_MAX_AFFILIATE_PROFILES = 5


def _normalize_iin(value: Any) -> str | None:
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) == 12:
        return digits
    return None


def _names_match(a: str, b: str) -> bool:
    left = a.strip().upper()
    right = b.strip().upper()
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _extract_director_iin(enrichment: dict, enriched: dict) -> str | None:
    """Try to find director IIN from enrichment, relation data, or affiliate tree."""
    company_info = enrichment.get("companyInfo") or {}
    director_name = str(company_info.get("director") or "").strip()

    for person in (enrichment.get("affiliates") or {}).get("individuals") or []:
        iin = _normalize_iin(person.get("iin"))
        if not iin:
            continue
        person_name = str(person.get("name") or "").strip()
        role = str(person.get("role") or "").lower()
        if "руковод" in role or "директор" in role:
            return iin
        if director_name and _names_match(director_name, person_name):
            return iin

    if director_name:
        for person in (enrichment.get("affiliates") or {}).get("individuals") or []:
            iin = _normalize_iin(person.get("iin"))
            if iin and _names_match(director_name, str(person.get("name") or "")):
                return iin

    relation = enriched.get("relationExtended") or {}
    by_head = relation.get("affiliation_by_head") or relation.get("affiliationByHead")
    if isinstance(by_head, dict):
        for key in (
            "head_biin",
            "head_biin_formatted",
            "head_iin",
            "head_bin",
            "head_bin_formatted",
            "director_iin",
            "headIin",
            "directorIin",
            "biin",
            "iinBin",
        ):
            iin = _normalize_iin(by_head.get(key))
            if iin:
                return iin

    for key in ("director_iin", "head_iin", "manager_iin", "directorIin", "headIin"):
        val = relation.get(key) or company_info.get(key)
        iin = _normalize_iin(val)
        if iin:
            return iin

    found = deep_find(relation, _DIRECTOR_IIN_KEYS)
    iin = _normalize_iin(found)
    if iin:
        return iin

    def _person_iin_from_tree(node: dict) -> str | None:
        if node.get("type") == "person":
            iin = _normalize_iin(node.get("iinBin"))
            if iin:
                role = str(node.get("role") or "").lower()
                child_name = str(node.get("name") or "")
                if "руковод" in role or "директор" in role:
                    return iin
                if director_name and _names_match(director_name, child_name):
                    return iin
        for child in node.get("children") or []:
            if isinstance(child, dict):
                found = _person_iin_from_tree(child)
                if found:
                    return found
        return None

    tree = enriched.get("affiliateTree") or {}
    root = tree.get("root") or {}
    if isinstance(root, dict):
        tree_iin = _person_iin_from_tree(root)
        if tree_iin:
            return tree_iin

    return None


def _company_data_from_info(iin: str, info_data: dict[str, Any], name_hint: str = "") -> CompanyData:
    mapped = map_info_data(iin, info_data, company_name=name_hint)
    fields = {key: mapped[key] for key in CompanyData.model_fields if key in mapped}
    company = CompanyData(**fields)
    company.raw = mapped.get("raw") or {}
    company.section_sources = mapped.get("section_sources") or company.section_sources
    return company


async def _fetch_enrichment_profile(iin: str, name_hint: str = "") -> dict[str, Any]:
    """Fetch Adata /info for *iin* and return normalized enrichment dict.

    Used for affiliate/director *summary* profiles only, so we skip the detailed
    court-case pagination (``merge_court_pages=False``) — the summary needs just
    aggregated court totals, not the per-page case detail.
    """
    info_data = await fetch_company_info(iin, merge_court_pages=False)
    company = _company_data_from_info(iin, info_data, name_hint=name_hint)
    display = name_hint or company.name or ""
    return company_data_to_enrichment(display, company)


def _affiliate_profile_summary(enrichment: dict[str, Any]) -> dict[str, Any]:
    info = enrichment.get("companyInfo") or {}
    return {
        "name": info.get("fullName") or info.get("name"),
        "director": info.get("director"),
        "director_iin": info.get("director_iin"),
        "courts": enrichment.get("courts"),
        "taxes": enrichment.get("taxes"),
        "riskFlags": enrichment.get("riskFlags") or [],
        "operatingStatus": info.get("operatingStatus"),
    }


async def _build_affiliate_profile(bin_val: str) -> dict[str, Any]:
    result = await _fetch_enrichment_profile(bin_val)
    summary = _affiliate_profile_summary(result)
    if not summary.get("director_iin"):
        summary["director_iin"] = await fetch_director_iin(bin_val)
    return summary


def _build_individual_courts_meta(
    iin_val: str,
    *,
    main_director_iin: str | None,
    enrichment: dict[str, Any],
    affiliate_profiles: dict[str, Any],
) -> dict[str, str | None]:
    if main_director_iin and iin_val == main_director_iin:
        return {
            "name": (enrichment.get("companyInfo") or {}).get("director"),
            "role": "Директор основной компании",
        }
    for bin_val, profile in affiliate_profiles.items():
        if profile.get("director_iin") == iin_val:
            return {
                "name": profile.get("director"),
                "role": "Директор аффилиата",
                "companyBin": bin_val,
                "companyName": profile.get("name") or profile.get("company_name"),
            }
    return {"name": None, "role": "Директор"}


async def _fetch_individual_courts_for_case(
    enrichment: dict[str, Any],
    affiliate_profiles: dict[str, Any],
    main_bin: str,
    *,
    case_id: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, str | None]]]:
    company_info = enrichment.get("companyInfo") or {}
    main_director_iin = _normalize_iin(company_info.get("director_iin"))
    if not main_director_iin and main_bin:
        main_director_iin = await fetch_director_iin(main_bin)
        if main_director_iin:
            company_info["director_iin"] = main_director_iin
            enrichment["companyInfo"] = company_info

    level1_iins = [
        _normalize_iin(profile.get("director_iin"))
        for profile in affiliate_profiles.values()
        if profile.get("director_iin")
    ]
    level1_iins = [iin for iin in level1_iins if iin][:4]

    all_iins: list[str] = []
    seen: set[str] = set()
    for candidate in [main_director_iin, *level1_iins]:
        if candidate and candidate not in seen:
            seen.add(candidate)
            all_iins.append(candidate)
        if len(all_iins) >= 5:
            break

    if not all_iins:
        return {}, {}

    results = await asyncio.gather(
        *[fetch_individual_court_cases(iin_val, case_id=case_id) for iin_val in all_iins],
        return_exceptions=True,
    )

    individual_courts: dict[str, list[dict[str, Any]]] = {}
    individual_courts_meta: dict[str, dict[str, str | None]] = {}
    for iin_val, result in zip(all_iins, results):
        if isinstance(result, BaseException):
            logger.warning("fetch_individual_court_cases failed for %s: %s", iin_val, result)
            individual_courts[iin_val] = []
        else:
            individual_courts[iin_val] = result if isinstance(result, list) else []
        individual_courts_meta[iin_val] = _build_individual_courts_meta(
            iin_val,
            main_director_iin=main_director_iin,
            enrichment=enrichment,
            affiliate_profiles=affiliate_profiles,
        )

    return individual_courts, individual_courts_meta


def _collect_nonresident_nodes_from_tree(tree_root: dict | None) -> list[dict]:
    """Walk the affiliate tree and collect all nodes without a valid KZ BIN."""
    if not tree_root:
        return []

    targets: list[dict] = []

    def _walk(node: dict, depth: int = 0) -> None:
        if depth > 3:
            return
        iin_bin = str(node.get("iinBin") or "").strip()
        name = str(node.get("name") or "").strip()

        if name and (not iin_bin or not _KZ_BIN_RE.match(iin_bin)):
            node_type = str(node.get("type") or "")
            if node_type != "main":
                role = str(node.get("role") or "")
                etype = (
                    "INDIVIDUAL"
                    if node_type == "person" and "юрлицо" not in role.lower()
                    else "ORGANISATION"
                )
                targets.append(
                    {
                        "name": name,
                        "entity_type": etype,
                        "key": iin_bin or name[:60],
                        "role": role,
                        "level": node.get("level", depth),
                    }
                )

        for child in node.get("children") or []:
            _walk(child, depth + 1)

    _walk(tree_root)
    return targets


def _build_lseg_extended_targets(enriched: dict) -> list[dict]:
    """Collect non-resident LSEG targets from enrichment, Adata extras, and affiliate tree."""
    lseg_targets: list[dict] = []
    enrichment = enriched.get("enrichment") or {}
    beneficiary = enriched.get("beneficiary")
    non_residents = enriched.get("nonResidents")

    for item in beneficiary if isinstance(beneficiary, list) else []:
        ctype = str(item.get("counterparty_type") or item.get("counterpartyType") or "")
        if ctype and ctype.upper() != "KZ":
            name = str(item.get("name") or item.get("short_name") or "")
            if name:
                raw_type = str(item.get("type") or item.get("entity_type") or "ORGANISATION").upper()
                etype = (
                    "INDIVIDUAL"
                    if "INDIVIDUAL" in raw_type or "PERSON" in raw_type
                    else "ORGANISATION"
                )
                biin = str(item.get("biin") or item.get("iin") or "")
                lseg_targets.append(
                    {"name": name, "entity_type": etype, "key": biin or name[:40]}
                )

    for item in ((non_residents if isinstance(non_residents, dict) else {}).get("data") or []):
        name = str(item.get("name") or item.get("short_name") or "")
        if name:
            raw_type = str(item.get("type") or item.get("entity_type") or "ORGANISATION").upper()
            etype = (
                "INDIVIDUAL"
                if "INDIVIDUAL" in raw_type or "PERSON" in raw_type
                else "ORGANISATION"
            )
            key = str(item.get("biin") or item.get("iin") or name[:40])
            lseg_targets.append({"name": name, "entity_type": etype, "key": key})

    affiliates_data = enrichment.get("affiliates") or {}
    for ind in affiliates_data.get("individuals") or []:
        iin_val = str(ind.get("iin") or "").strip()
        name = str(ind.get("name") or "").strip()
        if name and not iin_val:
            lseg_targets.append(
                {"name": name, "entity_type": "ORGANISATION", "key": name[:60]}
            )
    for comp in affiliates_data.get("companies") or []:
        bin_val = str(comp.get("iinBin") or comp.get("bin") or "").strip()
        name = str(comp.get("name") or "").strip()
        if name and (not bin_val or not _KZ_BIN_RE.match(bin_val)):
            lseg_targets.append(
                {"name": name, "entity_type": "ORGANISATION", "key": bin_val or name[:60]}
            )

    affiliate_tree_root = (enriched.get("affiliateTree") or {}).get("root")
    lseg_targets.extend(_collect_nonresident_nodes_from_tree(affiliate_tree_root))

    seen_keys: set[str] = set()
    unique_targets: list[dict] = []
    for t in lseg_targets:
        key = t["key"]
        if key not in seen_keys:
            seen_keys.add(key)
            unique_targets.append(t)
    return unique_targets


async def _run_lseg_extended_screening(
    case_id: str, unique_targets: list[dict]
) -> dict:
    """Screen targets via LSEG batch and return lsegExtended dict."""
    if not unique_targets or not lseg_service.is_available():
        return {}
    try:
        batch_raw = await lseg_service.screen_batch(unique_targets, case_id=case_id)
        lseg_extended = build_lseg_extended_entities(unique_targets, batch_raw)
        screened = sum(1 for v in lseg_extended.values() if isinstance(v, dict))
        logger.info(
            "LSEG screen_batch for %s: %d targets → %d entities in lsegExtended",
            case_id,
            len(unique_targets),
            screened,
        )
        return lseg_extended
    except Exception as exc:
        logger.warning("LSEG screen_batch failed for %s: %s", case_id, exc)
        return {}


async def process_case(case_id: str) -> None:
    """Adata enrichment + LSEG screening. AI conclusion queued separately."""
    row = db.get_case(case_id)
    if row is None:
        return

    company_name = row["company_name"]
    iin = row["iin"]

    try:
        db.update_case(case_id, status="enriching")
        enrichment_svc = EnrichmentService()
        company_data, sources, data_sources = await enrichment_svc.enrich(iin, case_id=case_id)

        enrichment = company_data_to_enrichment(company_name, company_data)
        assessment = build_assessment(enrichment)
        screen_name = resolve_company_display_name(company_name, iin, enrichment)

        existing = row.get("enriched_data") or {}
        if not isinstance(existing, dict):
            existing = {}
        existing = add_event_to_enriched(
            existing,
            provider="Pipeline",
            action="process_case:start",
            subject={"type": "BIN", "value": iin, "name": company_name},
            outcome={"status": "ok"},
        )

        courts = enrichment.get("courts") or {}
        director = enrichment.get("companyInfo", {}).get("director")
        main_bin = _normalize_iin(iin) or iin

        async def _maybe_analyze_courts() -> list | None:
            if courts.get("cases"):
                return await analyze_court_cases(courts["cases"], iin=iin)
            return None

        # ── Core wave: court analysis + LSEG company screen + BIN-only Adata
        # fetches. Everything here needs only the main BIN / core enrichment, so
        # the case reaches "ready" fast; affiliate / director / individual
        # profiles are deferred to process_case_deep_dive().
        (
            analyzed_court_cases,
            lseg_data,
            trustworthy_plus,
            beneficiary,
            non_residents,
            relation_extended,
            company_court_cases,
        ) = await asyncio.gather(
            _maybe_analyze_courts(),
            lseg_service.screen(company_name=screen_name, director=director, iin=iin, case_id=case_id),
            fetch_trustworthy_plus(iin, case_id=case_id),
            fetch_beneficiary(iin, case_id=case_id),
            fetch_non_resident_affiliations(iin, case_id=case_id),
            fetch_relation_extended(iin, case_id=case_id),
            fetch_company_court_cases(main_bin, case_id=case_id),
            return_exceptions=True,
        )

        # Unpack / handle exceptions from the core wave
        if isinstance(analyzed_court_cases, BaseException):
            logger.warning("analyze_court_cases failed: %s", analyzed_court_cases)
            analyzed_court_cases = None
        if analyzed_court_cases is not None:
            courts["cases"] = analyzed_court_cases
            enrichment["courts"] = courts

        if isinstance(lseg_data, BaseException):
            logger.warning("lseg.screen failed for %s: %s", case_id, lseg_data)
            lseg_data = None
        if isinstance(trustworthy_plus, BaseException):
            logger.warning("fetch_trustworthy_plus failed for %s: %s", case_id, trustworthy_plus)
            trustworthy_plus = {}
        if isinstance(beneficiary, BaseException):
            logger.warning("fetch_beneficiary failed for %s: %s", case_id, beneficiary)
            beneficiary = []
        if isinstance(non_residents, BaseException):
            logger.warning("fetch_non_resident_affiliations failed for %s: %s", case_id, non_residents)
            non_residents = {"hasNonResidentFromAll": False, "data": []}
        if isinstance(relation_extended, BaseException):
            logger.warning("fetch_relation_extended failed for %s: %s", case_id, relation_extended)
            relation_extended = {}
        if isinstance(company_court_cases, BaseException):
            logger.warning("fetch_company_court_cases failed: %s", company_court_cases)
            company_court_cases = []

        if company_court_cases:
            existing = add_event_to_enriched(
                existing,
                provider="Adata",
                action="company_courts:summary",
                subject={"type": "BIN", "value": iin},
                outcome={
                    "status": "ok",
                    "counts": {
                        "cases": len(company_court_cases),
                        "docs": sum(
                            len(c.get("documents") or [])
                            + sum(
                                len(h.get("documents") or [])
                                for h in (c.get("history") or [])
                                if isinstance(h, dict)
                            )
                            for c in company_court_cases
                        ),
                    },
                },
            )

        resolved_name = _resolved_company_name(company_name, iin, enrichment)

        latest_row = db.get_case(case_id) or {}
        latest_enriched = latest_row.get("enriched_data") if isinstance(latest_row, dict) else {}
        latest_enriched = latest_enriched if isinstance(latest_enriched, dict) else {}
        verification_log = latest_enriched.get("verificationLog") or existing.get("verificationLog")

        # Preserve any previously generated full report so that re-running the
        # pipeline (e.g. "Refresh" on the case detail page) does not erase it.
        full_report = latest_enriched.get("fullReport") or existing.get("fullReport")
        full_report_ts = (
            latest_enriched.get("fullReportGeneratedAt")
            or existing.get("fullReportGeneratedAt")
        )

        db.update_case(
            case_id,
            status="ready",
            company_name=resolved_name,
            enriched_data={
                **({"verificationLog": verification_log} if verification_log else {}),
                **({"fullReport": full_report, "fullReportGeneratedAt": full_report_ts} if full_report else {}),
                "enrichment": enrichment,
                "assessment": assessment,
                "lseg": lseg_data,
                "dataSources": data_sources,
                "affiliateTree": _empty_tree_meta(),
                "trustworthyPlus": trustworthy_plus if isinstance(trustworthy_plus, dict) else {},
                "beneficiary": beneficiary if isinstance(beneficiary, list) else [],
                "nonResidents": non_residents if isinstance(non_residents, dict) else {"hasNonResidentFromAll": False, "data": []},
                "relationExtended": relation_extended if isinstance(relation_extended, dict) else {},
                "companyCourtCases": company_court_cases,
                "deepDiveStatus": "pending",
            },
            sources=sources,
            conclusion="",
        )
    except Exception:
        logger.exception("Case processing failed for %s", case_id)
        db.update_case(case_id, status="error")


async def process_case_deep_dive(case_id: str) -> None:
    """Deferred heavy follow-up after :func:`process_case`.

    Fetches affiliate / director / individual profiles, individual court cases
    and LSEG extended screening for non-resident affiliates, merges them into
    ``enriched_data`` and flips ``deepDiveStatus`` to ``ready``. The case is
    already "ready" with core facts, so this runs in the background while the UI
    shows a loading state for these sections. Chained before the tree / AI jobs
    so there is only ever one ``enriched_data`` writer at a time.
    """
    row = db.get_case(case_id)
    if row is None or row.get("status") != "ready":
        return
    enriched = row.get("enriched_data")
    if not isinstance(enriched, dict):
        return
    enrichment = enriched.get("enrichment") or {}
    if not enrichment:
        db.update_case(case_id, enriched_data={**enriched, "deepDiveStatus": "ready"})
        return

    iin = row["iin"]
    main_bin = _normalize_iin(iin) or iin

    try:
        affiliates_data = enrichment.get("affiliates") or {}
        beneficiary = enriched.get("beneficiary") if isinstance(enriched.get("beneficiary"), list) else []
        non_residents = enriched.get("nonResidents") if isinstance(enriched.get("nonResidents"), dict) else {}

        affiliate_bins: list[str] = []
        seen_bins: set[str] = {main_bin} if main_bin else set()
        for comp in affiliates_data.get("companies") or []:
            bin_val = _normalize_iin(comp.get("iinBin") or comp.get("bin"))
            if not bin_val or bin_val in seen_bins:
                continue
            seen_bins.add(bin_val)
            affiliate_bins.append(bin_val)
            if len(affiliate_bins) >= _MAX_AFFILIATE_PROFILES:
                break

        founder_iins: list[str] = []
        for person in affiliates_data.get("individuals") or []:
            p_iin = _normalize_iin(person.get("iin"))
            if p_iin and not person.get("is_company"):
                founder_iins.append(p_iin)
        _dir_iin_for_profiles = _normalize_iin(enrichment.get("companyInfo", {}).get("director_iin"))
        all_person_iins: list[str] = []
        seen_person: set[str] = set()
        for candidate in [_dir_iin_for_profiles, *founder_iins]:
            if candidate and candidate not in seen_person:
                seen_person.add(candidate)
                all_person_iins.append(candidate)
            if len(all_person_iins) >= 6:
                break

        _director_iin_early = _extract_director_iin(enrichment, {})

        async def _fetch_director_profile_early() -> tuple[str | None, dict[str, Any]]:
            if not _director_iin_early:
                return None, {}
            try:
                profile = await _fetch_enrichment_profile(
                    _director_iin_early,
                    name_hint=str(enrichment.get("companyInfo", {}).get("director") or ""),
                )
                return _director_iin_early, profile
            except Exception as exc:
                logger.warning("Director profile fetch failed: %s", exc)
                return _director_iin_early, {}

        async def _fetch_all_affiliate_profiles() -> dict[str, Any]:
            if not affiliate_bins:
                return {}
            results = await asyncio.gather(
                *[_build_affiliate_profile(b) for b in affiliate_bins],
                return_exceptions=True,
            )
            profiles: dict[str, Any] = {}
            for b, r in zip(affiliate_bins, results):
                if isinstance(r, BaseException):
                    logger.warning("Affiliate profile failed for %s: %s", b, r)
                elif isinstance(r, dict):
                    profiles[b] = r
            return profiles

        async def _fetch_all_individual_profiles() -> dict[str, dict[str, Any]]:
            if not all_person_iins:
                return {}
            results = await asyncio.gather(
                *[fetch_individual_info(p, case_id=case_id) for p in all_person_iins],
                return_exceptions=True,
            )
            profiles: dict[str, dict[str, Any]] = {}
            for p, r in zip(all_person_iins, results):
                if isinstance(r, BaseException):
                    logger.warning("fetch_individual_info failed for %s: %s", p, r)
                elif isinstance(r, dict) and r:
                    profiles[p] = r
            return profiles

        # ── Deep wave A: director + affiliate + individual profiles in parallel ──
        (
            _director_iin_and_profile,
            affiliate_profiles,
            individual_profiles,
        ) = await asyncio.gather(
            _fetch_director_profile_early(),
            _fetch_all_affiliate_profiles(),
            _fetch_all_individual_profiles(),
            return_exceptions=True,
        )

        if isinstance(_director_iin_and_profile, BaseException):
            logger.warning("director profile fetch failed: %s", _director_iin_and_profile)
            _director_iin_and_profile = (None, {})
        if isinstance(affiliate_profiles, BaseException):
            logger.warning("affiliate profiles failed: %s", affiliate_profiles)
            affiliate_profiles = {}
        if isinstance(individual_profiles, BaseException):
            logger.warning("individual profiles failed: %s", individual_profiles)
            individual_profiles = {}

        _fetched_director_iin, director_profile = _director_iin_and_profile  # type: ignore[misc]
        director_event_iin = _fetched_director_iin

        # If enrichment-only path didn't find director_iin, retry using the stored
        # relationExtended / affiliateTree (already in enriched_data).
        if not _fetched_director_iin:
            director_iin = _extract_director_iin(enrichment, enriched)
            if director_iin:
                try:
                    director_profile = await _fetch_enrichment_profile(
                        director_iin,
                        name_hint=str(enrichment.get("companyInfo", {}).get("director") or ""),
                    )
                except Exception as exc:
                    logger.warning("Director profile fallback fetch failed: %s", exc)
                    director_profile = {}
                director_event_iin = director_iin

        # ── Deep wave B: lseg_extended + individual_courts in parallel ──
        partial_enriched = {
            "enrichment": enrichment,
            "beneficiary": beneficiary,
            "nonResidents": non_residents,
        }
        unique_targets = _build_lseg_extended_targets(partial_enriched)

        lseg_extended_result, individual_courts_result = await asyncio.gather(
            _run_lseg_extended_screening(case_id, unique_targets),
            _fetch_individual_courts_for_case(enrichment, affiliate_profiles, main_bin, case_id=case_id),
            return_exceptions=True,
        )

        if isinstance(lseg_extended_result, BaseException):
            logger.warning("lseg_extended failed: %s", lseg_extended_result)
            lseg_extended = {}
        else:
            lseg_extended = lseg_extended_result

        if isinstance(individual_courts_result, BaseException):
            logger.warning("individual_courts failed: %s", individual_courts_result)
            individual_courts, individual_courts_meta = {}, {}
        else:
            individual_courts, individual_courts_meta = individual_courts_result

        if unique_targets and not lseg_extended and not lseg_service.is_available():
            logger.warning(
                "lsegExtended empty for %s: %d foreign-affiliate targets but LSEG is not configured",
                case_id,
                len(unique_targets),
            )
        if unique_targets and not lseg_extended and lseg_service.is_available():
            logger.warning(
                "lsegExtended empty for %s despite %d targets (batch returned no mappable results)",
                case_id,
                len(unique_targets),
            )

        total_individual_cases = sum(len(v) for v in individual_courts.values() if isinstance(v, list))

        # Merge into the LATEST enriched_data so we preserve core keys + any
        # verification events written by the fetches above, then mark complete.
        latest_row = db.get_case(case_id) or {}
        merged = latest_row.get("enriched_data") if isinstance(latest_row, dict) else {}
        merged = merged if isinstance(merged, dict) else {}
        if director_event_iin:
            merged = add_event_to_enriched(
                merged,
                provider="Adata",
                action="director_profile",
                subject={"type": "IIN", "value": director_event_iin},
                request={"endpoint": "/company/info (+ fallbacks)", "params": {"iinBin": director_event_iin}},
                outcome={"status": "ok"},
            )
        merged = add_event_to_enriched(
            merged,
            provider="Adata",
            action="individual_courts:summary",
            outcome={"status": "ok", "counts": {"iinChecked": len(individual_courts), "cases": total_individual_cases}},
        )
        merged.update(
            {
                "lsegExtended": lseg_extended,
                "directorProfile": director_profile,
                "affiliateProfiles": affiliate_profiles,
                "individualCourts": individual_courts,
                "individualCourtsMeta": individual_courts_meta,
                "individualProfiles": individual_profiles,
                "deepDiveStatus": "ready",
            }
        )
        db.update_case(case_id, enriched_data=merged)
    except Exception:
        logger.exception("Case deep-dive failed for %s", case_id)
        latest_row = db.get_case(case_id) or {}
        merged = latest_row.get("enriched_data") if isinstance(latest_row, dict) else {}
        merged = merged if isinstance(merged, dict) else {}
        db.update_case(case_id, enriched_data={**merged, "deepDiveStatus": "ready"})


async def rescreen_case_lseg(case_id: str, *, force: bool = False) -> bool:
    """Apply LSEG screening to an already-enriched case. Returns True on success."""
    row = db.get_case(case_id)
    if row is None or row.get("status") != "ready":
        return False

    enriched = row.get("enriched_data") or {}

    existing_lseg = enriched.get("lseg")
    if (
        not force
        and existing_lseg
        and existing_lseg.get("screenedAt")
    ):
        logger.debug("Skipping LSEG for %s — already screened (use force=True)", case_id)
        return True

    enrichment = enriched.get("enrichment") or {}
    company_name = row["company_name"]
    iin = row["iin"]
    screen_name = resolve_company_display_name(company_name, iin, enrichment)
    director = enrichment.get("companyInfo", {}).get("director")

    if force:
        await lseg_service.invalidate_screening_cache(screen_name, director)
        if screen_name != company_name:
            await lseg_service.invalidate_screening_cache(company_name, director)

    lseg_data = await lseg_service.screen(
        company_name=screen_name,
        director=director,
        iin=iin,
        case_id=case_id,
    )
    if lseg_data is None:
        return False

    enriched["lseg"] = lseg_data

    db.update_case(
        case_id,
        enriched_data=enriched,
    )
    logger.info("LSEG re-screen done for %s (force=%s)", case_id, force)
    return True


async def rescreen_lseg_extended(case_id: str) -> dict:
    """Re-run LSEG batch screening for all non-resident targets including affiliate tree."""
    row = db.get_case(case_id)
    if row is None:
        return {"status": "error", "message": "Case not found", "screened": 0, "targets": 0}

    enriched = row.get("enriched_data") or {}
    unique_targets = _build_lseg_extended_targets(enriched)

    if not unique_targets:
        logger.info("rescreen_lseg_extended: no targets for %s", case_id)
        return {
            "status": "ok",
            "screened": 0,
            "targets": 0,
            "sanctionHits": 0,
            "entities": [],
        }

    if not lseg_service.is_available():
        return {
            "status": "error",
            "message": "LSEG is not configured",
            "screened": 0,
            "targets": len(unique_targets),
        }

    lseg_extended = await _run_lseg_extended_screening(case_id, unique_targets)
    enriched["lsegExtended"] = lseg_extended
    db.update_case(case_id, enriched_data=enriched)

    entities_summary: list[dict] = []
    sanction_hits = 0
    for key, entity in lseg_extended.items():
        if not isinstance(entity, dict):
            continue
        on_list = bool(entity.get("isOnSanctionList"))
        if on_list:
            sanction_hits += 1
        entities_summary.append(
            {
                "key": key,
                "name": entity.get("name"),
                "role": entity.get("role"),
                "isOnSanctionList": on_list,
                "sanctionLists": entity.get("sanctionLists") or [],
            }
        )

    logger.info(
        "rescreen_lseg_extended done for %s: %d targets, %d screened, %d sanction hits",
        case_id,
        len(unique_targets),
        len(lseg_extended),
        sanction_hits,
    )
    return {
        "status": "ok",
        "screened": len(lseg_extended),
        "targets": len(unique_targets),
        "sanctionHits": sanction_hits,
        "entities": entities_summary,
    }
