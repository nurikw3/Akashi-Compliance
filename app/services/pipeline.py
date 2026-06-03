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
from app.services.risk.scoring import RiskScorer
from app.services.ai.court_analyzer import analyze_court_cases
from app.services.verification_log import add_event_to_enriched

from app.services.company_display import resolve_company_display_name

logger = logging.getLogger(__name__)


def _resolved_company_name(company_name: str, iin: str, enrichment: dict[str, Any]) -> str:
    return resolve_company_display_name(company_name, iin, enrichment)

_scorer = RiskScorer()
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
    """Fetch Adata /info for *iin* and return normalized enrichment dict."""
    info_data = await fetch_company_info(iin)
    company = _company_data_from_info(iin, info_data, name_hint=name_hint)
    display = name_hint or company.name or ""
    return company_data_to_enrichment(display, company)


def _affiliate_profile_summary(enrichment: dict[str, Any]) -> dict[str, Any]:
    info = enrichment.get("companyInfo") or {}
    return {
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
                "role": f"Директор аффилиата ({bin_val})",
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
    """Adata enrichment + LSEG screening + unified scoring. AI conclusion queued separately."""
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

        # LLM-classify court cases (enriches courts.cases[].aiAnalysis)
        courts = enrichment.get("courts") or {}
        if courts.get("cases"):
            courts["cases"] = await analyze_court_cases(courts["cases"])
            enrichment["courts"] = courts

        # LSEG screening: company + director
        director = enrichment.get("companyInfo", {}).get("director")
        lseg_data = await lseg_service.screen(
            company_name=screen_name,
            director=director,
            iin=iin,
            case_id=case_id,
        )

        # Unified 7-metric scoring
        affiliate_tree = existing.get("affiliateTree")
        scoring = _scorer.calculate(enrichment, lseg_data, affiliate_tree)
        assessment["riskLevel"] = scoring.risk_level

        # Parallel extended data: trustworthy-plus, beneficiary, non-residents, relation
        trustworthy_plus, beneficiary, non_residents, relation_extended = await asyncio.gather(
            fetch_trustworthy_plus(iin, case_id=case_id),
            fetch_beneficiary(iin, case_id=case_id),
            fetch_non_resident_affiliations(iin, case_id=case_id),
            fetch_relation_extended(iin, case_id=case_id),
            return_exceptions=True,
        )

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

        partial_enriched = {
            "enrichment": enrichment,
            "beneficiary": beneficiary if isinstance(beneficiary, list) else [],
            "nonResidents": non_residents if isinstance(non_residents, dict) else {},
        }
        unique_targets = _build_lseg_extended_targets(partial_enriched)
        affiliates_data = enrichment.get("affiliates") or {}

        lseg_extended = await _run_lseg_extended_screening(case_id, unique_targets)
        if unique_targets and not lseg_extended and not lseg_service.is_available():
            logger.warning(
                "lsegExtended empty for %s: %d foreign-affiliate targets but LSEG is not configured",
                case_id,
                len(unique_targets),
            )
        partial_enriched_for_iin = {
            "enrichment": enrichment,
            "relationExtended": relation_extended if isinstance(relation_extended, dict) else {},
            "affiliateTree": affiliate_tree if isinstance(affiliate_tree, dict) else {},
        }
        director_iin = _extract_director_iin(enrichment, partial_enriched_for_iin)
        director_profile: dict[str, Any] = {}
        if director_iin:
            try:
                director_profile = await _fetch_enrichment_profile(
                    director_iin,
                    name_hint=str(enrichment.get("companyInfo", {}).get("director") or ""),
                )
                logger.info("Director profile fetched for IIN %s", director_iin)
                existing = add_event_to_enriched(
                    existing,
                    provider="Adata",
                    action="director_profile",
                    subject={"type": "IIN", "value": director_iin},
                    request={"endpoint": "/company/info (+ fallbacks)", "params": {"iinBin": director_iin}},
                    outcome={"status": "ok"},
                )
            except Exception as exc:
                logger.warning("Director profile fetch failed: %s", exc)
                director_profile = {}
                existing = add_event_to_enriched(
                    existing,
                    provider="Adata",
                    action="director_profile",
                    subject={"type": "IIN", "value": director_iin},
                    request={"endpoint": "/company/info (+ fallbacks)", "params": {"iinBin": director_iin}},
                    outcome={"status": "error", "message": str(exc)[:200]},
                )

        main_bin = _normalize_iin(iin) or iin
        affiliate_bins: list[str] = []
        seen_bins: set[str] = {main_bin} if main_bin else set()
        for comp in (enrichment.get("affiliates") or {}).get("companies") or []:
            bin_val = _normalize_iin(comp.get("iinBin") or comp.get("bin"))
            if not bin_val or bin_val in seen_bins:
                continue
            seen_bins.add(bin_val)
            affiliate_bins.append(bin_val)
            if len(affiliate_bins) >= _MAX_AFFILIATE_PROFILES:
                break

        affiliate_profiles: dict[str, Any] = {}
        if affiliate_bins:
            results = await asyncio.gather(
                *[_build_affiliate_profile(bin_val) for bin_val in affiliate_bins],
                return_exceptions=True,
            )
            for bin_val, result in zip(affiliate_bins, results):
                if isinstance(result, BaseException):
                    logger.warning("Affiliate profile failed for %s: %s", bin_val, result)
                elif isinstance(result, dict):
                    affiliate_profiles[bin_val] = result

        individual_courts, individual_courts_meta = await _fetch_individual_courts_for_case(
            enrichment,
            affiliate_profiles,
            main_bin,
            case_id=case_id,
        )

        company_court_cases = await fetch_company_court_cases(
            main_bin, case_id=case_id
        )

        total_individual_cases = sum(len(v) for v in individual_courts.values() if isinstance(v, list))
        existing = add_event_to_enriched(
            existing,
            provider="Adata",
            action="individual_courts:summary",
            outcome={"status": "ok", "counts": {"iinChecked": len(individual_courts), "cases": total_individual_cases}},
        )
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

        if not unique_targets:
            nr_count = len((non_residents if isinstance(non_residents, dict) else {}).get("data") or [])
            ben_foreign = sum(
                1
                for item in (beneficiary if isinstance(beneficiary, list) else [])
                if str(item.get("counterparty_type") or item.get("counterpartyType") or "").upper() != "KZ"
            )
            aff_no_bin = sum(
                1
                for ind in (affiliates_data.get("individuals") or [])
                if str(ind.get("name") or "").strip() and not str(ind.get("iin") or "").strip()
            )
            aff_foreign_co = sum(
                1
                for comp in (affiliates_data.get("companies") or [])
                if str(comp.get("name") or "").strip()
                and (
                    not str(comp.get("iinBin") or comp.get("bin") or "").strip()
                    or not str(comp.get("iinBin") or comp.get("bin") or "").strip().isdigit()
                    or len(str(comp.get("iinBin") or comp.get("bin") or "").strip()) != 12
                )
            )
            logger.info(
                "lsegExtended skipped for %s (BIN %s): no LSEG targets — "
                "nonResidents=%d, foreignBeneficiaries=%d, affiliatesNoBin=%d, foreignCompanies=%d",
                case_id,
                iin,
                nr_count,
                ben_foreign,
                aff_no_bin,
                aff_foreign_co,
            )

        if unique_targets and not lseg_extended and lseg_service.is_available():
            logger.warning(
                "lsegExtended empty for %s despite %d targets (batch returned no mappable results)",
                case_id,
                len(unique_targets),
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
            risk_level=scoring.risk_level,
            enriched_data={
                **({"verificationLog": verification_log} if verification_log else {}),
                **({"fullReport": full_report, "fullReportGeneratedAt": full_report_ts} if full_report else {}),
                "enrichment": enrichment,
                "assessment": assessment,
                "lseg": lseg_data,
                "scoreBreakdown": scoring.breakdown_as_dicts(),
                "totalScore": scoring.total_score,
                "dataSources": data_sources,
                "affiliateTree": _empty_tree_meta(),
                "trustworthyPlus": trustworthy_plus if isinstance(trustworthy_plus, dict) else {},
                "beneficiary": beneficiary if isinstance(beneficiary, list) else [],
                "nonResidents": non_residents if isinstance(non_residents, dict) else {"hasNonResidentFromAll": False, "data": []},
                "relationExtended": relation_extended if isinstance(relation_extended, dict) else {},
                "lsegExtended": lseg_extended,
                "directorProfile": director_profile,
                "affiliateProfiles": affiliate_profiles,
                "individualCourts": individual_courts,
                "individualCourtsMeta": individual_courts_meta,
                "companyCourtCases": company_court_cases,
            },
            sources=sources,
            conclusion="",
        )
    except Exception:
        logger.exception("Case processing failed for %s", case_id)
        db.update_case(case_id, status="error")


async def rescreen_case_lseg(case_id: str, *, force: bool = False) -> bool:
    """Apply LSEG screening + re-score to an already-enriched case. Returns True on success."""
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

    affiliate_tree = enriched.get("affiliateTree")
    scoring = _scorer.calculate(enrichment, lseg_data, affiliate_tree)

    assessment = enriched.get("assessment") or {}
    assessment["riskLevel"] = scoring.risk_level

    enriched["lseg"] = lseg_data
    enriched["scoreBreakdown"] = scoring.breakdown_as_dicts()
    enriched["totalScore"] = scoring.total_score
    enriched["assessment"] = assessment

    db.update_case(
        case_id,
        risk_level=scoring.risk_level,
        enriched_data=enriched,
    )
    logger.info(
        "LSEG re-screen done for %s: score=%.1f risk=%s (force=%s)",
        case_id,
        scoring.total_score,
        scoring.risk_level,
        force,
    )
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
