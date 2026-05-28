from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.models import db
from app.models.schemas import AuditDetail
from app.services.adata.client import AdataError, download_company_report, run_parallel_checks


GREEN_STATUS = "Совпадений не найдено"
RED_STATUS = "Совпадения найдены"


def build_audit_hash(organization_name: str, bin_value: str) -> str:
    raw_value = f"{organization_name.strip().lower()}{bin_value.strip().lower()}"
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def _collect_boolean_flags(value: Any) -> list[bool]:
    flags: list[bool] = []
    if isinstance(value, bool):
        return [value]
    if isinstance(value, dict):
        for nested_value in value.values():
            flags.extend(_collect_boolean_flags(nested_value))
    elif isinstance(value, list):
        for nested_value in value:
            flags.extend(_collect_boolean_flags(nested_value))
    return flags


def resolve_status(riskfactor_payload: dict[str, Any]) -> str:
    risk_data = riskfactor_payload.get("data", riskfactor_payload)
    flags = _collect_boolean_flags(risk_data)
    if not flags:
        raise ValueError("Riskfactor payload does not contain any boolean flags.")
    return GREEN_STATUS if all(flag is False for flag in flags) else RED_STATUS


def to_audit_detail(record: dict[str, Any], *, from_cache: bool) -> AuditDetail:
    pdf_path = record.get("pdf_path")
    return AuditDetail(
        id=record["id"],
        audit_hash=record["audit_hash"],
        checked_at=record["checked_at"],
        organization_name=record["organization_name"],
        bin=record["bin"],
        status=record["status"],
        from_cache=from_cache,
        raw_result=record["raw_result"],
        pdf_path=pdf_path,
        pdf_ready=bool(pdf_path),
    )


def _build_pdf_path(record: dict[str, Any]) -> Path:
    safe_timestamp = record["checked_at"].replace(":", "-").replace(".", "-")
    return settings.pdf_dir / f"audit_{record['id']}_{record['bin']}_{safe_timestamp}.pdf"


async def ensure_pdf_for_audit(
    record: dict[str, Any],
    *,
    raise_on_error: bool = False,
) -> dict[str, Any]:
    if record["status"] != RED_STATUS:
        return record

    existing_pdf_path = record.get("pdf_path")
    if existing_pdf_path and Path(existing_pdf_path).exists():
        return record

    pdf_path = _build_pdf_path(record)
    try:
        saved_path = await download_company_report(record["bin"], pdf_path)
    except AdataError:
        if raise_on_error:
            raise
        return record

    db.update_pdf_path(record["id"], str(saved_path))
    record["pdf_path"] = str(saved_path)
    return record


async def run_or_load_audit(organization_name: str, bin_value: str) -> AuditDetail:
    audit_hash = build_audit_hash(organization_name, bin_value)
    cached = db.get_audit_by_hash(audit_hash)
    if cached is not None:
        return to_audit_detail(cached, from_cache=True)

    raw_result = await run_parallel_checks(bin_value)
    risk_payload = raw_result.get("riskfactor") or {}
    if not risk_payload.get("data") and isinstance(raw_result.get("info"), dict):
        info_data = raw_result["info"].get("data") or {}
        if isinstance(info_data.get("riskfactor"), dict):
            risk_payload = {"data": info_data["riskfactor"]}
        elif info_data:
            risk_payload = {"data": info_data}
    status = resolve_status(risk_payload)

    saved = db.save_audit(
        audit_hash=audit_hash,
        organization_name=organization_name,
        bin_value=bin_value,
        checked_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        raw_result=raw_result,
    )
    saved = await ensure_pdf_for_audit(saved)
    return to_audit_detail(saved, from_cache=False)
