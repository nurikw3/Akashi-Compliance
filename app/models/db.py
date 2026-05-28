from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from app.core.config import settings


def ensure_storage() -> None:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    ensure_storage()
    connection = sqlite3.connect(settings.sqlite_path)
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                iin TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                risk_level TEXT,
                enriched_data TEXT,
                sources TEXT DEFAULT '[]',
                conclusion TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                analysis TEXT,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
            )
            """
        )
        _migrate_cases_columns(connection)
        connection.commit()


def _migrate_cases_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(cases)").fetchall()
    }
    if "parent_case_id" not in columns:
        connection.execute(
            """
            ALTER TABLE cases
            ADD COLUMN parent_case_id TEXT
            REFERENCES cases(id) ON DELETE SET NULL
            """
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_case(
    *,
    company_name: str,
    iin: str,
    parent_case_id: str | None = None,
) -> dict[str, Any]:
    case_id = str(uuid.uuid4())
    created_at = _now_iso()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO cases (id, company_name, iin, status, created_at, parent_case_id)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (case_id, company_name, iin, created_at, parent_case_id),
        )
        connection.commit()
    row = get_case(case_id)
    assert row is not None
    return row


def list_cases() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, company_name, iin, status, risk_level, enriched_data,
                   sources, conclusion, created_at, parent_case_id
            FROM cases
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [_deserialize_case(row) for row in rows]


def find_case_by_iin(iin: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, company_name, iin, status, risk_level, enriched_data,
                   sources, conclusion, created_at, parent_case_id
            FROM cases
            WHERE iin = ?
            ORDER BY
                CASE status WHEN 'ready' THEN 0 WHEN 'enriching' THEN 1 ELSE 2 END,
                created_at DESC
            LIMIT 1
            """,
            (iin,),
        ).fetchone()
    if row is None:
        return None
    return _deserialize_case(row)


def get_case(case_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, company_name, iin, status, risk_level, enriched_data,
                   sources, conclusion, created_at, parent_case_id
            FROM cases
            WHERE id = ?
            """,
            (case_id,),
        ).fetchone()
    if row is None:
        return None
    return _deserialize_case(row)


def update_case(case_id: str, **fields: Any) -> None:
    allowed = {
        "status",
        "risk_level",
        "enriched_data",
        "sources",
        "conclusion",
        "company_name",
        "iin",
        "parent_case_id",
    }
    updates: list[str] = []
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key in ("enriched_data", "sources") and value is not None:
            value = json.dumps(value, ensure_ascii=False)
        updates.append(f"{key} = ?")
        values.append(value)
    if not updates:
        return
    values.append(case_id)
    with get_connection() as connection:
        connection.execute(
            f"UPDATE cases SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        connection.commit()


def _deserialize_case(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    enriched = payload.get("enriched_data")
    if isinstance(enriched, str) and enriched:
        payload["enriched_data"] = json.loads(enriched)
    elif enriched is None:
        payload["enriched_data"] = None
    sources = payload.get("sources")
    if isinstance(sources, str):
        payload["sources"] = json.loads(sources) if sources else []
    return payload


def list_documents(case_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, case_id, filename, file_type, analysis, uploaded_at
            FROM documents
            WHERE case_id = ?
            ORDER BY uploaded_at DESC
            """,
            (case_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_document(
    *,
    case_id: str,
    filename: str,
    file_type: str,
    analysis: str | None = None,
) -> dict[str, Any]:
    doc_id = str(uuid.uuid4())
    uploaded_at = _now_iso()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO documents (id, case_id, filename, file_type, analysis, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doc_id, case_id, filename, file_type, analysis, uploaded_at),
        )
        connection.commit()
    return {
        "id": doc_id,
        "case_id": case_id,
        "filename": filename,
        "file_type": file_type,
        "analysis": analysis,
        "uploaded_at": uploaded_at,
    }


def list_chat_messages(case_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, case_id, role, content, created_at
            FROM chat_messages
            WHERE case_id = ?
            ORDER BY created_at ASC
            """,
            (case_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_chat_message(*, case_id: str, role: str, content: str) -> dict[str, Any]:
    message_id = str(uuid.uuid4())
    created_at = _now_iso()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO chat_messages (id, case_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, case_id, role, content, created_at),
        )
        connection.commit()
    return {
        "id": message_id,
        "case_id": case_id,
        "role": role,
        "content": content,
        "created_at": created_at,
    }


# --- Legacy audits (Streamlit) ---


def _deserialize_audit(row: sqlite3.Row | None) -> dict[str, Any] | None:
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
            FROM audits
            WHERE audit_hash = ?
            """,
            (audit_hash,),
        ).fetchone()
    return _deserialize_audit(row)


def get_audit_by_id(audit_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, audit_hash, organization_name, bin, checked_at, status, raw_json, pdf_path
            FROM audits
            WHERE id = ?
            """,
            (audit_id,),
        ).fetchone()
    return _deserialize_audit(row)


def list_audits(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, checked_at, organization_name, bin, status, pdf_path
            FROM audits
            ORDER BY checked_at DESC
            LIMIT ?
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
    pdf_path: str | None = None,
) -> dict[str, Any]:
    serialized = json.dumps(raw_result, ensure_ascii=False)
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
                serialized,
                pdf_path,
            ),
        )
        connection.commit()
        audit_id = int(cursor.lastrowid)
    saved = get_audit_by_id(audit_id)
    if saved is None:
        raise RuntimeError("Audit saved but not found")
    return saved


def update_pdf_path(audit_id: int, pdf_path: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE audits SET pdf_path = ? WHERE id = ?",
            (pdf_path, audit_id),
        )
        connection.commit()
