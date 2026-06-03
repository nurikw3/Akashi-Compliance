from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings
from app.core.auth import hash_password


def ensure_storage() -> None:
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    ensure_storage()
    with psycopg.connect(settings.database_url, row_factory=dict_row) as connection:
        yield connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audits (
                id SERIAL PRIMARY KEY,
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
                created_at TEXT NOT NULL,
                parent_case_id TEXT REFERENCES cases(id) ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                analysis TEXT,
                uploaded_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
    _ensure_admin_user()


def _ensure_admin_user() -> None:
    """Create or refresh the single admin user from env (password hash only in DB)."""
    username = settings.admin_username.strip()
    password = settings.admin_password
    if not username or not password:
        return

    password_hash = hash_password(password)
    created_at = _now_iso()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id FROM users WHERE username = %s",
            (username,),
        ).fetchone()
        if row is None:
            connection.execute(
                """
                INSERT INTO users (username, password_hash, created_at)
                VALUES (%s, %s, %s)
                """,
                (username, password_hash, created_at),
            )
        else:
            connection.execute(
                """
                UPDATE users SET password_hash = %s WHERE username = %s
                """,
                (password_hash, username),
            )
        connection.commit()


def get_user_by_username(username: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE username = %s",
            (username,),
        ).fetchone()
    return dict(row) if row else None


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
            VALUES (%s, %s, %s, 'pending', %s, %s)
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


def search_cases_by_name(name: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search cases by company name using ILIKE."""
    pattern = f"%{name}%"
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, company_name, iin, status, risk_level, enriched_data,
                   sources, conclusion, created_at, parent_case_id
            FROM cases
            WHERE company_name ILIKE %s
               OR (
                   enriched_data IS NOT NULL
                   AND enriched_data <> ''
                   AND enriched_data::jsonb->>'company_name' ILIKE %s
               )
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (pattern, pattern, limit),
        ).fetchall()
    return [_deserialize_case(row) for row in rows]


def search_cases_by_director(name: str, limit: int = 10) -> list[dict[str, Any]]:
    """Find cases where the director name contains the given string."""
    pattern = f"%{name}%"
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, company_name, iin, status, risk_level, enriched_data,
                   sources, conclusion, created_at, parent_case_id
            FROM cases
            WHERE enriched_data IS NOT NULL
              AND enriched_data <> ''
              AND (
                enriched_data::jsonb->'enrichment'->'companyInfo'->>'director' ILIKE %s
              )
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (pattern, limit),
        ).fetchall()
    return [_deserialize_case(row) for row in rows]


def find_cases_by_risk_level(risk_level: str, limit: int = 20) -> list[dict[str, Any]]:
    """Find cases by risk level."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, company_name, iin, status, risk_level, enriched_data,
                   sources, conclusion, created_at, parent_case_id
            FROM cases
            WHERE risk_level = %s AND status = 'ready'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (risk_level, limit),
        ).fetchall()
    return [_deserialize_case(row) for row in rows]


def find_case_by_iin(iin: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, company_name, iin, status, risk_level, enriched_data,
                   sources, conclusion, created_at, parent_case_id
            FROM cases
            WHERE iin = %s
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
            WHERE id = %s
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
        updates.append(f"{key} = %s")
        values.append(value)
    if not updates:
        return
    values.append(case_id)
    with get_connection() as connection:
        connection.execute(
            f"UPDATE cases SET {', '.join(updates)} WHERE id = %s",
            values,
        )
        connection.commit()


def _deserialize_case(row: dict[str, Any]) -> dict[str, Any]:
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
            WHERE case_id = %s
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
            VALUES (%s, %s, %s, %s, %s, %s)
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
            WHERE case_id = %s
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
            VALUES (%s, %s, %s, %s, %s)
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


def _deserialize_audit(row: dict[str, Any] | None) -> dict[str, Any] | None:
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
            WHERE audit_hash = %s
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
            WHERE id = %s
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
            LIMIT %s
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
        row = connection.execute(
            """
            INSERT INTO audits (audit_hash, organization_name, bin, checked_at, status, raw_json, pdf_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
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
        ).fetchone()
        connection.commit()
        if row is None:
            raise RuntimeError("Audit insert did not return id")
        audit_id = int(row["id"])
    saved = get_audit_by_id(audit_id)
    if saved is None:
        raise RuntimeError("Audit saved but not found")
    return saved


def update_pdf_path(audit_id: int, pdf_path: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE audits SET pdf_path = %s WHERE id = %s",
            (pdf_path, audit_id),
        )
        connection.commit()
