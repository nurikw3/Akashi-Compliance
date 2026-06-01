from __future__ import annotations

from typing import Any

from app.models import db
from app.services.enrichment.sources import default_section_sources


def case_to_api(row: dict[str, Any]) -> dict[str, Any]:
    enriched = row.get("enriched_data") or {}
    enrichment = enriched.get("enrichment")
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
        "riskLevel": row.get("risk_level"),
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
        "scoreBreakdown": enriched.get("scoreBreakdown"),
        "totalScore": enriched.get("totalScore"),
    }
