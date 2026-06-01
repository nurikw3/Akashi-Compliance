from __future__ import annotations

import logging

from app.models import db
from app.services.affiliate_tree import _empty_tree_meta
from app.services.enrichment.mapper import (
    build_assessment,
    company_data_to_enrichment,
)
from app.services.enrichment.service import EnrichmentService
from app.services.enrichment.sources import default_section_sources
import app.services.lseg.service as lseg_service
from app.services.risk.scoring import RiskScorer
from app.services.ai.court_analyzer import analyze_court_cases

logger = logging.getLogger(__name__)

_scorer = RiskScorer()


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
        company_data, sources, data_sources = await enrichment_svc.enrich(iin)

        enrichment = company_data_to_enrichment(company_name, company_data)
        assessment = build_assessment(enrichment)

        # LLM-classify court cases (enriches courts.cases[].aiAnalysis)
        courts = enrichment.get("courts") or {}
        if courts.get("cases"):
            courts["cases"] = await analyze_court_cases(courts["cases"])
            enrichment["courts"] = courts

        # LSEG screening: company + director
        director = enrichment.get("companyInfo", {}).get("director")
        lseg_data = await lseg_service.screen(
            company_name=company_name,
            director=director,
        )

        # Unified 7-metric scoring
        existing = row.get("enriched_data") or {}
        affiliate_tree = existing.get("affiliateTree")
        scoring = _scorer.calculate(enrichment, lseg_data, affiliate_tree)
        assessment["riskLevel"] = scoring.risk_level

        db.update_case(
            case_id,
            status="ready",
            risk_level=scoring.risk_level,
            enriched_data={
                "enrichment": enrichment,
                "assessment": assessment,
                "lseg": lseg_data,
                "scoreBreakdown": scoring.breakdown_as_dicts(),
                "totalScore": scoring.total_score,
                "dataSources": data_sources,
                "affiliateTree": _empty_tree_meta(),
            },
            sources=sources,
            conclusion="",
        )
    except Exception:
        logger.exception("Case processing failed for %s", case_id)
        try:
            stub = EnrichmentService()._stub  # noqa: SLF001
            company_data = await stub.check(iin)
            enrichment = company_data_to_enrichment(company_name, company_data)
            assessment = build_assessment(enrichment)
            scoring = _scorer.calculate(enrichment, None)
            assessment["riskLevel"] = scoring.risk_level

            db.update_case(
                case_id,
                status="ready",
                risk_level=scoring.risk_level,
                enriched_data={
                    "enrichment": enrichment,
                    "assessment": assessment,
                    "lseg": None,
                    "scoreBreakdown": scoring.breakdown_as_dicts(),
                    "totalScore": scoring.total_score,
                    "dataSources": default_section_sources(["stub"]),
                    "affiliateTree": _empty_tree_meta(),
                },
                sources=["stub"],
                conclusion="",
            )
        except Exception:
            logger.exception("Stub fallback failed for %s", case_id)
            db.update_case(case_id, status="error")


async def rescreen_case_lseg(case_id: str) -> bool:
    """Apply LSEG screening + re-score to an already-enriched case. Returns True on success."""
    row = db.get_case(case_id)
    if row is None or row.get("status") != "ready":
        return False

    enriched = row.get("enriched_data") or {}

    # Skip if already screened
    existing_lseg = enriched.get("lseg")
    if existing_lseg and existing_lseg.get("screenedAt"):
        logger.debug("Skipping LSEG for %s — already screened", case_id)
        return True

    enrichment = enriched.get("enrichment") or {}
    company_name = row["company_name"]
    director = enrichment.get("companyInfo", {}).get("director")

    lseg_data = await lseg_service.screen(
        company_name=company_name,
        director=director,
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
        "LSEG re-screen done for %s: score=%.1f risk=%s",
        case_id,
        scoring.total_score,
        scoring.risk_level,
    )
    return True
