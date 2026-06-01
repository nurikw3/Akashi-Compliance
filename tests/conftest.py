"""Isolate tests from developer PostgreSQL data."""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

import psycopg
from psycopg import sql

_DEFAULT_TEST_DB = "akashicompliance_test"
_DEFAULT_URL = (
    "postgresql://akashicompliance:akashicompliance@127.0.0.1:5432/akashicompliance"
)


def _test_database_url() -> str:
    base = os.getenv("DATABASE_URL", _DEFAULT_URL)
    parsed = urlparse(base)
    return urlunparse(parsed._replace(path=f"/{_DEFAULT_TEST_DB}"))


def _ensure_test_database() -> None:
    parsed = urlparse(_test_database_url())
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    with psycopg.connect(admin_url, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (_DEFAULT_TEST_DB,),
        ).fetchone()
        if not exists:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(_DEFAULT_TEST_DB))
            )


_test_url = _test_database_url()
os.environ["DATABASE_URL"] = _test_url
os.environ["AUTH_ENABLED"] = "false"

try:
    _ensure_test_database()
except psycopg.OperationalError:
    pass

from app.models import db as _db  # noqa: E402

try:
    _db.init_db()
except psycopg.OperationalError as exc:
    raise RuntimeError(
        "PostgreSQL is required for tests. Start it with: docker compose up -d postgres"
    ) from exc
