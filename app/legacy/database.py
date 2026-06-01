"""Legacy Streamlit audit helpers — backed by the shared PostgreSQL database."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models import db as _db


def ensure_storage() -> None:
    _db.ensure_storage()


def init_db() -> None:
    _db.init_db()


def get_audit_by_hash(audit_hash: str) -> dict[str, Any] | None:
    return _db.get_audit_by_hash(audit_hash)


def get_audit_by_id(audit_id: int) -> dict[str, Any] | None:
    return _db.get_audit_by_id(audit_id)


def list_audits(limit: int = 100) -> list[dict[str, Any]]:
    return _db.list_audits(limit=limit)


def save_audit(
    *,
    audit_hash: str,
    organization_name: str,
    bin_value: str,
    checked_at: str,
    status: str,
    raw_result: dict[str, Any],
    pdf_path: Path | None = None,
) -> dict[str, Any]:
    return _db.save_audit(
        audit_hash=audit_hash,
        organization_name=organization_name,
        bin_value=bin_value,
        checked_at=checked_at,
        status=status,
        raw_result=raw_result,
        pdf_path=str(pdf_path) if pdf_path else None,
    )


def update_pdf_path(audit_id: int, pdf_path: Path) -> None:
    _db.update_pdf_path(audit_id, str(pdf_path))
