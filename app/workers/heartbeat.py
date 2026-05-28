"""Worker liveness heartbeat in Redis (used for API fallback when no worker runs)."""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

WORKER_HEARTBEAT_KEY = "akashicompliance:worker:heartbeat"


async def refresh_worker_heartbeat() -> None:
    if not settings.redis_url:
        return
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        try:
            await client.set(
                WORKER_HEARTBEAT_KEY,
                "1",
                ex=settings.worker_heartbeat_ttl_seconds,
            )
        finally:
            await client.aclose()
    except Exception:
        logger.debug("Failed to refresh worker heartbeat", exc_info=True)


async def worker_heartbeat_ok() -> bool:
    if not settings.redis_url:
        return False
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        try:
            return bool(await client.exists(WORKER_HEARTBEAT_KEY))
        finally:
            await client.aclose()
    except Exception:
        return False
