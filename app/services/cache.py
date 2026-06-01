"""Universal Redis cache wrapper for LSEG and Adata results."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

LSEG_TTL = 86400   # 24 h
ADATA_TTL = 43200  # 12 h

_client: aioredis.Redis | None = None  # process-level singleton


def _get_client() -> aioredis.Redis:
    global _client  # noqa: PLW0603
    if _client is None:
        _client = aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            decode_responses=True,
        )
    return _client


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------


def lseg_key(name: str, entity_type: str) -> str:
    """``lseg:v1:{name_normalized}:{entity_type}``"""
    name_normalized = name.lower().strip().replace(" ", "_")
    return f"lseg:v1:{name_normalized}:{entity_type}"


def adata_key(endpoint: str, iin: str) -> str:
    """``adata:v1:{endpoint}:{iin}``

    *endpoint* is one of: ``info``, ``trustworthy``, ``beneficiary``, ``nonresident``,
    ``relation``.
    """
    return f"adata:v1:{endpoint}:{iin}"


# ---------------------------------------------------------------------------
# Generic cache operations
# ---------------------------------------------------------------------------


async def get_cached(key: str) -> dict[str, Any] | None:
    """Return cached value for *key*, or ``None`` on cache-miss / error."""
    try:
        client = _get_client()
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)  # type: ignore[no-any-return]
    except Exception as exc:
        logger.warning("Redis get failed for key=%r: %s", key, exc)
        return None


async def set_cached(key: str, data: dict[str, Any], ttl: int) -> None:
    """Serialise *data* as JSON and store under *key* with *ttl* seconds."""
    try:
        client = _get_client()
        await client.setex(key, ttl, json.dumps(data, ensure_ascii=False))
    except Exception as exc:
        logger.warning("Redis set failed for key=%r: %s", key, exc)


async def delete_cached(key: str) -> None:
    """Remove *key* from the cache (no-op on miss / error)."""
    try:
        client = _get_client()
        await client.delete(key)
    except Exception as exc:
        logger.warning("Redis delete failed for key=%r: %s", key, exc)
