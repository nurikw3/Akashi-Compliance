#!/usr/bin/env python3
"""One-time migration: copy data from SQLite compliance.db into PostgreSQL."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.models import db  # noqa: E402


def _sqlite_path() -> Path:
    return settings.sqlite_path


def _copy_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn: psycopg.Connection,
    *,
    table: str,
    columns: list[str],
    conflict_column: str | None = None,
) -> int:
    col_list = ", ".join(columns)
    placeholders = ", ".join("%s" for _ in columns)
    rows = sqlite_conn.execute(
        f"SELECT {col_list} FROM {table}"
    ).fetchall()
    if not rows:
        return 0
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
    if conflict_column:
        updates = ", ".join(
            f"{col} = EXCLUDED.{col}" for col in columns if col != conflict_column
        )
        sql += f" ON CONFLICT ({conflict_column}) DO UPDATE SET {updates}"
    count = 0
    with pg_conn.cursor() as cur:
        for row in rows:
            cur.execute(sql, row)
            count += 1
    return count


def migrate() -> None:
    sqlite_path = _sqlite_path()
    if not sqlite_path.is_file():
        print(f"No SQLite database at {sqlite_path}; nothing to migrate.")
        return

    print(f"Migrating from {sqlite_path} -> PostgreSQL")
    db.init_db()

    cases = documents = messages = audits = 0
    sqlite_conn = sqlite3.connect(sqlite_path)
    try:
        with psycopg.connect(settings.database_url) as pg_conn:
            pg_conn.execute("SET session_replication_role = replica")
            cases = _copy_table(
                sqlite_conn,
                pg_conn,
                table="cases",
                columns=[
                    "id",
                    "company_name",
                    "iin",
                    "status",
                    "risk_level",
                    "enriched_data",
                    "sources",
                    "conclusion",
                    "created_at",
                    "parent_case_id",
                ],
                conflict_column="id",
            )
            documents = _copy_table(
                sqlite_conn,
                pg_conn,
                table="documents",
                columns=[
                    "id",
                    "case_id",
                    "filename",
                    "file_type",
                    "analysis",
                    "uploaded_at",
                ],
                conflict_column="id",
            )
            messages = _copy_table(
                sqlite_conn,
                pg_conn,
                table="chat_messages",
                columns=["id", "case_id", "role", "content", "created_at"],
                conflict_column="id",
            )
            audits = _copy_table(
                sqlite_conn,
                pg_conn,
                table="audits",
                columns=[
                    "id",
                    "audit_hash",
                    "organization_name",
                    "bin",
                    "checked_at",
                    "status",
                    "raw_json",
                    "pdf_path",
                ],
                conflict_column="audit_hash",
            )
            if audits:
                pg_conn.execute(
                    """
                    SELECT setval(
                        pg_get_serial_sequence('audits', 'id'),
                        COALESCE((SELECT MAX(id) FROM audits), 1)
                    )
                    """
                )
            pg_conn.execute("SET session_replication_role = DEFAULT")
            pg_conn.commit()
    finally:
        sqlite_conn.close()

    print(
        f"Done: cases={cases}, documents={documents}, "
        f"chat_messages={messages}, audits={audits}"
    )


if __name__ == "__main__":
    migrate()
