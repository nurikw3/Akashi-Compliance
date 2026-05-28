from __future__ import annotations

import logging

from app.models import db
from app.services.affiliate_tree import _empty_tree_meta
from app.services.enrichment.mapper import (
    build_assessment,
    company_data_to_enrichment,
    risk_from_company_data,
)
from app.services.enrichment.service import EnrichmentService

logger = logging.getLogger(__name__)


async def process_case(case_id: str) -> None:
    """Adata enrichment only; AI conclusion is queued separately."""
    row = db.get_case(case_id)
    if row is None:
        return

    company_name = row["company_name"]
    iin = row["iin"]

    try:
        db.update_case(case_id, status="enriching")
        enrichment_service = EnrichmentService()
        company_data, sources, data_sources = await enrichment_service.enrich(iin)

        enrichment = company_data_to_enrichment(company_name, company_data)
        assessment = build_assessment(enrichment)
        risk = risk_from_company_data(company_data)
        assessment["riskLevel"] = risk.value

        db.update_case(
            case_id,
            status="ready",
            risk_level=risk.value,
            enriched_data={
                "enrichment": enrichment,
                "assessment": assessment,
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
            from app.services.enrichment.sources import default_section_sources

            db.update_case(
                case_id,
                status="ready",
                risk_level=assessment["riskLevel"],
                enriched_data={
                    "enrichment": enrichment,
                    "assessment": assessment,
                    "dataSources": default_section_sources(["stub"]),
                    "affiliateTree": _empty_tree_meta(),
                },
                sources=["stub"],
                conclusion="",
            )
        except Exception:
            logger.exception("Stub fallback failed for %s", case_id)
            db.update_case(case_id, status="error")
