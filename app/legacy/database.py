from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.core.config import settings


AUDIT_DB = settings.sqlite_path.parent / "audit_cache.db"


def ensure_storage() -> None:
    AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    ensure_storage()
    connection = sqlite3.connect(AUDIT_DB)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_hash TEXT NOT NULL UNIQUE,
                organization_name TEXT NOT NULL,
                bin TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                status TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                pdf_path TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audits_checked_at
            ON audits (checked_at DESC)
            """
        )
        connection.commit()


def _deserialize_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    payload["raw_result"] = json.loads(payload.pop("raw_json"))
    return payload


def get_audit_by_hash(audit_hash: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, audit_hash, organization_name, bin, checked_at, status, raw_json, pdf_path
            FROM audits WHERE audit_hash = ?
            """,
            (audit_hash,),
        ).fetchone()
    return _deserialize_row(row)


def get_audit_by_id(audit_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, audit_hash, organization_name, bin, checked_at, status, raw_json, pdf_path
            FROM audits WHERE id = ?
            """,
            (audit_id,),
        ).fetchone()
    return _deserialize_row(row)


def list_audits(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, checked_at, organization_name, bin, status, pdf_path
            FROM audits ORDER BY checked_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


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
    serialized_payload = json.dumps(raw_result, ensure_ascii=False)
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO audits (audit_hash, organization_name, bin, checked_at, status, raw_json, pdf_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_hash,
                organization_name,
                bin_value,
                checked_at,
                status,
                serialized_payload,
                str(pdf_path) if pdf_path else None,
            ),
        )
        connection.commit()
        audit_id = int(cursor.lastrowid)
    saved = get_audit_by_id(audit_id)
    if saved is None:
        raise RuntimeError("Audit was saved but could not be loaded.")
    return saved


def update_pdf_path(audit_id: int, pdf_path: Path) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE audits SET pdf_path = ? WHERE id = ?",
            (str(pdf_path), audit_id),
        )
        connection.commit()
