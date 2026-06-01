from __future__ import annotations

from typing import Any

from app.services.enrichment.base import CompanyData

ENRICHMENT_SECTIONS = (
    "companyInfo",
    "taxes",
    "courts",
    "sanctions",
    "affiliates",
    "graph",
    "assessment",
    "conclusion",
)

SourceKind = str  # "adata" | "none"


def _endpoint_ok(raw: dict[str, Any], key: str) -> bool:
    section = raw.get(key)
    if not isinstance(section, dict):
        return False
    if section.get("error"):
        return False
    return section.get("data") is not None


def infer_section_sources_from_data(data: CompanyData, provider: str) -> dict[str, str]:
    """Infer per-section provider from CompanyData.raw and populated fields."""
    raw = data.raw or {}
    explicit = raw.get("_section_sources")
    if isinstance(explicit, dict):
        return {
            section: "none" if explicit.get(section) in (None, "stub") else explicit.get(section, "none")
            for section in ENRICHMENT_SECTIONS
        }

    sources: dict[str, str] = {section: "none" for section in ENRICHMENT_SECTIONS}

    if (
        _endpoint_ok(raw, "info")
        or _endpoint_ok(raw, "basic")
        or data.name
        or data.director
        or data.address
    ):
        sources["companyInfo"] = "adata"

    if _endpoint_ok(raw, "info") or _endpoint_ok(raw, "riskfactor") or data.tax_debt is not None:
        sources["taxes"] = "adata"

    courts_from_courtcase = _endpoint_ok(raw, "courtcase")
    courts_from_info = _endpoint_ok(raw, "info") and (
        data.court_cases is not None or data.court_cases_years
    )
    courts_from_risk = data.court_cases is not None and _endpoint_ok(raw, "riskfactor")
    if courts_from_courtcase or courts_from_info or data.court_cases_years or courts_from_risk:
        sources["courts"] = "adata"
    if raw.get("_courts_source") in ("stub", "none"):
        sources["courts"] = "none"

    sanctions_ok = _endpoint_ok(raw, "trustworthy_extended") or _endpoint_ok(raw, "sanctions")
    if sanctions_ok or _endpoint_ok(raw, "info") or data.in_sanctions_list is not None:
        sources["sanctions"] = "adata"

    if _endpoint_ok(raw, "info") or _endpoint_ok(raw, "relation") or data.related_companies or data.founders:
        sources["affiliates"] = "adata"
        sources["graph"] = "adata"

    sources["assessment"] = "none"
    sources["conclusion"] = "none"
    return sources


def merge_section_sources(*maps: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {section: "none" for section in ENRICHMENT_SECTIONS}
    for source_map in maps:
        for section, kind in source_map.items():
            if section not in merged:
                continue
            if kind == "adata":
                merged[section] = "adata"
    merged["assessment"] = "none"
    merged["conclusion"] = "none"
    if merged.get("affiliates") == "adata":
        merged["graph"] = "adata"
    return merged


def default_section_sources(case_sources: list[str] | None = None) -> dict[str, str]:
    """Fallback when only case-level provider list is stored."""
    kind: SourceKind = "adata" if case_sources and "adata" in case_sources else "none"
    return {section: kind for section in ENRICHMENT_SECTIONS} | {
        "assessment": "none",
        "conclusion": "none",
    }
