"""Enqueue heavy work to TaskIQ (Redis) or run inline when queue is disabled."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.workers.heartbeat import worker_heartbeat_ok

logger = logging.getLogger(__name__)


def _taskiq_configured() -> bool:
    return settings.task_queue_enabled and bool(settings.redis_url)


async def resolve_queue_backend() -> tuple[str, str | None]:
    """
    Pick runtime backend: ``taskiq`` or ``inline``.
    Returns (backend, optional_warning_message).
    """
    if not _taskiq_configured():
        return "inline", None

    if not await ping_redis():
        return (
            "inline",
            "Redis недоступен — задачи выполняются в процессе API (inline).",
        )

    if not await worker_heartbeat_ok():
        return (
            "inline",
            "TaskIQ worker не обнаружен — задачи выполняются в процессе API (inline). "
            "Запустите: uv run akashicompliance-worker",
        )

    return "taskiq", None


async def _run_enrichment_inline(case_id: str) -> None:
    from app.services.pipeline import process_case

    await process_case(case_id)


async def _run_tree_inline(case_id: str) -> None:
    from app.services.affiliate_tree import build_affiliate_tree

    await build_affiliate_tree(case_id)


async def _run_ai_conclusion_inline(case_id: str) -> None:
    from app.services.ai.jobs import generate_conclusion_for_case

    await generate_conclusion_for_case(case_id)


async def _run_chat_inline(case_id: str, user_message: str) -> None:
    from app.services.ai.jobs import chat_reply_for_case

    await chat_reply_for_case(case_id, user_message)


async def _schedule_ai_conclusion_after_enrichment(case_id: str, *, use_taskiq: bool) -> None:
    from app.models import db

    row = db.get_case(case_id)
    if not row or row.get("status") != "ready":
        return

    if use_taskiq:
        from app.workers.tasks import ai_conclusion_task

        await ai_conclusion_task.kiq(case_id)
        logger.info("Queued ai_conclusion for %s after enrichment", case_id)
    else:
        asyncio.create_task(_run_ai_conclusion_inline(case_id))


async def _schedule_tree_after_enrichment(case_id: str, *, use_taskiq: bool) -> None:
    from app.models import db

    row = db.get_case(case_id)
    if not row or row.get("status") != "ready":
        return

    if use_taskiq:
        from app.workers.tasks import affiliate_tree_task

        await affiliate_tree_task.kiq(case_id)
        logger.info("Queued affiliate_tree for %s after enrichment", case_id)
    else:
        asyncio.create_task(_run_tree_inline(case_id))


async def _run_enrichment_then_followups_inline(case_id: str) -> None:
    await _run_enrichment_inline(case_id)
    await _schedule_tree_after_enrichment(case_id, use_taskiq=False)
    await _schedule_ai_conclusion_after_enrichment(case_id, use_taskiq=False)


def _job_result(
    *,
    mode: str,
    queue: str,
    task_id: str | None,
    warning: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "mode": mode,
        "taskId": task_id,
        "queue": queue,
    }
    if warning:
        result["warning"] = warning
        result["fallback"] = mode == "inline" and _taskiq_configured()
    return result


async def enqueue_case_pipeline(case_id: str) -> dict[str, Any]:
    """
    Enrichment first (``case_pipeline``), then affiliate tree in a separate job.
    Returns {mode, taskId?, queue, warning?} for API responses.
    """
    backend, warning = await resolve_queue_backend()
    if warning:
        logger.warning("%s", warning)

    if backend == "taskiq":
        from app.workers.tasks import case_pipeline_task

        issued = await case_pipeline_task.kiq(case_id)
        task_id = issued.task_id if hasattr(issued, "task_id") else str(issued)
        logger.info("Queued case_pipeline for %s (task_id=%s)", case_id, task_id)
        return _job_result(
            mode="taskiq",
            queue="case_pipeline",
            task_id=task_id,
            warning=warning,
        )

    asyncio.create_task(_run_enrichment_then_followups_inline(case_id))
    logger.info("Inline enrichment+followups for %s (no worker or fallback)", case_id)
    return _job_result(
        mode="inline",
        queue="case_pipeline",
        task_id=None,
        warning=warning,
    )


async def enqueue_affiliate_tree(case_id: str) -> dict[str, Any]:
    backend, warning = await resolve_queue_backend()
    if warning:
        logger.warning("%s", warning)

    if backend == "taskiq":
        from app.workers.tasks import affiliate_tree_task

        issued = await affiliate_tree_task.kiq(case_id)
        task_id = issued.task_id if hasattr(issued, "task_id") else str(issued)
        logger.info("Queued affiliate_tree for %s (task_id=%s)", case_id, task_id)
        return _job_result(
            mode="taskiq",
            queue="affiliate_tree",
            task_id=task_id,
            warning=warning,
        )

    asyncio.create_task(_run_tree_inline(case_id))
    return _job_result(
        mode="inline",
        queue="affiliate_tree",
        task_id=None,
        warning=warning,
    )


async def enqueue_ai_conclusion(case_id: str) -> dict[str, Any]:
    backend, warning = await resolve_queue_backend()
    if warning:
        logger.warning("%s", warning)

    if backend == "taskiq":
        from app.workers.tasks import ai_conclusion_task

        issued = await ai_conclusion_task.kiq(case_id)
        task_id = issued.task_id if hasattr(issued, "task_id") else str(issued)
        logger.info("Queued ai_conclusion for %s (task_id=%s)", case_id, task_id)
        return _job_result(
            mode="taskiq",
            queue="ai_conclusion",
            task_id=task_id,
            warning=warning,
        )

    asyncio.create_task(_run_ai_conclusion_inline(case_id))
    return _job_result(
        mode="inline",
        queue="ai_conclusion",
        task_id=None,
        warning=warning,
    )


async def enqueue_chat_reply(case_id: str, user_message: str) -> dict[str, Any]:
    backend, warning = await resolve_queue_backend()
    if warning:
        logger.warning("%s", warning)

    if backend == "taskiq":
        from app.workers.tasks import chat_reply_task

        issued = await chat_reply_task.kiq(case_id, user_message)
        task_id = issued.task_id if hasattr(issued, "task_id") else str(issued)
        logger.info("Queued chat_reply for %s (task_id=%s)", case_id, task_id)
        return _job_result(
            mode="taskiq",
            queue="chat_reply",
            task_id=task_id,
            warning=warning,
        )

    asyncio.create_task(_run_chat_inline(case_id, user_message))
    return _job_result(
        mode="inline",
        queue="chat_reply",
        task_id=None,
        warning=warning,
    )


async def ping_redis() -> bool:
    if not settings.redis_url:
        return False
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        try:
            return bool(await client.ping())
        finally:
            await client.aclose()
    except Exception:
        return False
