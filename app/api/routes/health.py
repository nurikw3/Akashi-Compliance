from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.services.queue import ping_redis, resolve_queue_backend
from app.workers.heartbeat import worker_heartbeat_ok

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    configured = settings.task_queue_enabled and bool(settings.redis_url)
    redis_ok = await ping_redis() if configured else None
    worker_ok = await worker_heartbeat_ok() if redis_ok else None
    active_backend, warning = await resolve_queue_backend()

    if configured and active_backend == "taskiq":
        backend_label = "taskiq+redis"
    elif configured and warning:
        backend_label = "inline-asyncio (fallback)"
    else:
        backend_label = "inline-asyncio"

    return {
        "status": "ok",
        "queue": {
            "enabled": settings.task_queue_enabled,
            "configured": configured,
            "backend": backend_label,
            "activeBackend": active_backend,
            "redisUrl": settings.redis_url if settings.task_queue_enabled else None,
            "redisOk": redis_ok,
            "workerOk": worker_ok,
            "warning": warning,
        },
    }
