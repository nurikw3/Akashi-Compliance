"""TaskIQ broker (Redis). Import ``tasks`` so decorators register on worker startup."""

from __future__ import annotations

from taskiq import InMemoryBroker
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.core.config import settings

if settings.task_queue_enabled and settings.redis_url:
    broker = ListQueueBroker(url=settings.redis_url)
    broker = broker.with_result_backend(
        RedisAsyncResultBackend(
            redis_url=settings.redis_url,
            result_ex_time=settings.task_result_ttl_seconds,
        )
    )
else:
    broker = InMemoryBroker()

__all__ = ["broker"]
