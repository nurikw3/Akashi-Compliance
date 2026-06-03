from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

_DEFAULT_ADATA_BASE_URL = "https://api.adata.kz/api/company"


def normalize_adata_base_url(url: str) -> str:
    """Ensure company API prefix; fix common ``/api`` without ``/company`` typo."""
    normalized = (url or "").strip().rstrip("/")
    if not normalized:
        return _DEFAULT_ADATA_BASE_URL
    if normalized.endswith("api.adata.kz"):
        return f"{normalized}/api/company"
    if normalized.endswith("/api") and not normalized.endswith("/api/company"):
        return f"{normalized}/company"
    return normalized


def normalize_adata_individual_base_url(company_base_url: str) -> str:
    """Derive Adata *individual* API base from the company base URL."""
    normalized = (company_base_url or "").strip().rstrip("/")
    if not normalized:
        return "https://api.adata.kz/api/individual"
    if normalized.endswith("/company"):
        return f"{normalized[: -len('/company')]}/individual"
    if normalized.endswith("/individual"):
        return normalized
    if "/api/individual" in normalized:
        idx = normalized.index("/api/individual")
        return normalized[: idx + len("/api/individual")]
    return "https://api.adata.kz/api/individual"


@dataclass
class Settings:
    adata_token: str = os.getenv("ADATA_TOKEN", "")
    adata_base_url: str = normalize_adata_base_url(
        os.getenv("ADATA_BASE_URL", _DEFAULT_ADATA_BASE_URL)
    )
    adata_timeout_seconds: float = float(os.getenv("ADATA_TIMEOUT_SECONDS", "30"))
    adata_poll_attempts: int = int(os.getenv("ADATA_POLL_ATTEMPTS", "10"))
    adata_poll_delay_seconds: float = float(os.getenv("ADATA_POLL_DELAY_SECONDS", "2"))
    graph_probe_concurrency: int = int(os.getenv("GRAPH_PROBE_CONCURRENCY", "3"))
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    task_queue_enabled: bool = os.getenv("TASK_QUEUE_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    task_result_ttl_seconds: int = int(os.getenv("TASK_RESULT_TTL_SECONDS", "3600"))
    taskiq_workers: int = max(1, int(os.getenv("TASKIQ_WORKERS", "1")))
    worker_heartbeat_ttl_seconds: int = int(
        os.getenv("WORKER_HEARTBEAT_TTL_SECONDS", "30")
    )
    worker_heartbeat_interval_seconds: int = int(
        os.getenv("WORKER_HEARTBEAT_INTERVAL_SECONDS", "10")
    )
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    lseg_client_id: str = os.getenv("LSEG_CLIENT_ID", "")
    lseg_client_secret: str = os.getenv("LSEG_CLIENT_SECRET", "")
    lseg_group_id: str = os.getenv("LSEG_GROUP_ID", "")
    suppress_enrichment_errors: bool = os.getenv(
        "SUPPRESS_ENRICHMENT_ERRORS",
        os.getenv("USE_STUB_ON_API_FAILURE", "false"),
    ).lower() in ("1", "true", "yes")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://akashicompliance:akashicompliance@127.0.0.1:5432/akashicompliance",
    )
    sqlite_path: Path = BASE_DIR / os.getenv("SQLITE_PATH", "data/compliance.db")
    pdf_dir: Path = BASE_DIR / os.getenv("PDF_DIR", "generated-pdfs")
    api_base_url: str = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:3001,http://127.0.0.1:3001",
        ).split(",")
        if origin.strip()
    )
    auth_enabled: bool = os.getenv("AUTH_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    admin_username: str = os.getenv("ADMIN_USERNAME", "nurikw3")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "Ak4sh1_Nurik_2026!")


settings = Settings()
