from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models import db
from app.models.schemas import AuditDetail, AuditHistoryItem, AuditRunRequest
from app.services.legacy_audits import (
    RED_STATUS,
    ensure_pdf_for_audit,
    run_or_load_audit,
    to_audit_detail,
)

router = APIRouter(prefix="/api/audits", tags=["audits"])


@router.post("/run", response_model=AuditDetail)
async def run_audit(payload: AuditRunRequest) -> AuditDetail:
    return await run_or_load_audit(payload.organization_name, payload.bin)


@router.get("/history", response_model=list[AuditHistoryItem])
def audit_history() -> list[AuditHistoryItem]:
    items = []
    for row in db.list_audits():
        items.append(
            AuditHistoryItem(
                id=row["id"],
                checked_at=row["checked_at"],
                organization_name=row["organization_name"],
                bin=row["bin"],
                status=row["status"],
                pdf_path=row.get("pdf_path"),
                pdf_ready=bool(row.get("pdf_path")),
            )
        )
    return items


@router.get("/{audit_id}", response_model=AuditDetail)
async def get_audit(audit_id: int) -> AuditDetail:
    record = db.get_audit_by_id(audit_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    if record["status"] == RED_STATUS:
        record = await ensure_pdf_for_audit(record)
    return to_audit_detail(record, from_cache=True)


@router.get("/{audit_id}/pdf")
async def download_audit_pdf(audit_id: int) -> FileResponse:
    record = db.get_audit_by_id(audit_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    if record["status"] != RED_STATUS:
        raise HTTPException(status_code=404, detail="PDF is only available for red audits")

    record = await ensure_pdf_for_audit(record, raise_on_error=True)
    pdf_path = record.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=Path(pdf_path).name,
    )
