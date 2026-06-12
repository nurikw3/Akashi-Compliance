from __future__ import annotations

import re

from typing import Any

from app.models import db
from app.services.enrichment.person import normalize_person_name
from app.services.enrichment.sources import default_section_sources

_ROLE_NAME = re.compile(r"\(([^)]+)\)")


def _repair_stale_director(enrichment: dict[str, Any] | None) -> dict[str, Any] | None:
    """Fix legacy rows where ``director`` was stored as str(riskFactor.head) blob."""
    if not enrichment:
        return enrichment
    info = enrichment.get("companyInfo")
    if not isinstance(info, dict):
        return enrichment
    current = info.get("director")
    if not isinstance(current, str) or not current.strip().startswith("{"):
        return enrichment

    profiles = enrichment.get("affiliateProfiles")
    if isinstance(profiles, dict):
        for profile in profiles.values():
            if isinstance(profile, dict):
                name = normalize_person_name(profile.get("director"))
                if name:
                    info["director"] = name
                    return enrichment

    for person in (enrichment.get("affiliates") or {}).get("individuals") or []:
        if not isinstance(person, dict):
            continue
        role = (person.get("role") or "").lower()
        if "учред" in role or "руковод" in role:
            name = normalize_person_name(person.get("name"))
            if name:
                info["director"] = name
                return enrichment

    for company in (enrichment.get("affiliates") or {}).get("companies") or []:
        if not isinstance(company, dict):
            continue
        name = normalize_person_name(company.get("director"))
        if name:
            info["director"] = name
            return enrichment
        role = company.get("role") or ""
        match = _ROLE_NAME.search(role)
        if match:
            name = normalize_person_name(match.group(1))
            if name:
                info["director"] = name
                return enrichment

    info["director"] = "—"
    return enrichment


def case_to_api(row: dict[str, Any]) -> dict[str, Any]:
    from app.services.ai.full_report_meta import full_report_meta_for_row

    enriched = row.get("enriched_data") or {}
    enrichment = _repair_stale_director(enriched.get("enrichment"))
    assessment = enriched.get("assessment")
    case_sources = row.get("sources") or []
    data_sources = enriched.get("dataSources") or default_section_sources(case_sources)

    documents = [
        {
            "id": doc["id"],
            "filename": doc["filename"],
            "fileType": doc["file_type"],
            "uploadedAt": doc["uploaded_at"],
        }
        for doc in db.list_documents(row["id"])
    ]
    chat_history = [
        {
            "id": msg["id"],
            "role": msg["role"],
            "content": msg["content"],
            "createdAt": msg["created_at"],
        }
        for msg in db.list_chat_messages(row["id"])
    ]

    return {
        "id": row["id"],
        "name": row["company_name"],
        "iinBin": row["iin"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "enrichment": enrichment,
        "assessment": assessment,
        "documents": documents,
        "chatHistory": chat_history,
        "conclusion": row.get("conclusion"),
        "sources": case_sources,
        "dataSources": data_sources,
        "affiliateTree": enriched.get("affiliateTree"),
        "parentCaseId": row.get("parent_case_id"),
        "lseg": enriched.get("lseg"),
        "lsegExtended": enriched.get("lsegExtended"),
        "osint": enriched.get("osint"),
        "osintStatus": enriched.get("osintStatus"),
        "directorProfile": enriched.get("directorProfile"),
        "affiliateProfiles": enriched.get("affiliateProfiles"),
        "individualCourts": enriched.get("individualCourts"),
        "individualCourtsMeta": enriched.get("individualCourtsMeta"),
        "companyCourtCases": enriched.get("companyCourtCases"),
        "individualProfiles": enriched.get("individualProfiles"),
        "deepDiveStatus": enriched.get("deepDiveStatus"),
        "verificationLog": enriched.get("verificationLog") or [],
        "hasFullReport": bool(enriched.get("fullReport")),
        "fullReportGeneratedAt": enriched.get("fullReportGeneratedAt"),
        "fullReportStatus": enriched.get("fullReportStatus"),
        **full_report_meta_for_row(row),
    }
