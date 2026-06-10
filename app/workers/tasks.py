"""Heavy jobs executed in TaskIQ worker process(es)."""

from __future__ import annotations

import asyncio
import logging

from taskiq import TaskiqEvents

from app.models import db
from app.services.affiliate_tree import build_affiliate_tree
from app.services.ai.jobs import chat_reply_for_case, generate_conclusion_for_case
from app.services.enrichment.providers.adata import AdataProvider
from app.services.enrichment.providers.kompra import KompraProvider
from app.services.enrichment.registry import registry
from app.services.pipeline import process_case, process_case_deep_dive
from app.workers.broker import broker
from app.workers.heartbeat import refresh_worker_heartbeat

logger = logging.getLogger(__name__)

_worker_ready = False
_heartbeat_task: asyncio.Task[None] | None = None


def _ensure_worker_context() -> None:
    global _worker_ready
    if _worker_ready:
        return
    db.init_db()
    if not registry.all():
        registry.register(AdataProvider())
        registry.register(KompraProvider())
    _worker_ready = True


async def _heartbeat_loop() -> None:
    from app.core.config import settings

    interval = settings.worker_heartbeat_interval_seconds
    while True:
        await refresh_worker_heartbeat()
        await asyncio.sleep(interval)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def worker_startup(_state: object) -> None:
    global _heartbeat_task
    _ensure_worker_context()
    await refresh_worker_heartbeat()
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())
    logger.info("TaskIQ worker started (providers + DB ready)")


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def worker_shutdown(_state: object) -> None:
    global _heartbeat_task
    if _heartbeat_task is not None:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
        _heartbeat_task = None


@broker.task(task_name="case_pipeline")
async def case_pipeline_task(case_id: str) -> dict[str, str]:
    """Core enrichment via Adata; deep-dive, tree and AI conclusion are chained."""
    _ensure_worker_context()
    logger.info("case_pipeline (enrichment) start: %s", case_id)
    await process_case(case_id)
    row = db.get_case(case_id)
    if row and row.get("status") == "ready":
        await case_deep_dive_task.kiq(case_id)
        logger.info("case_pipeline queued case_deep_dive for %s", case_id)
    logger.info("case_pipeline (enrichment) done: %s", case_id)
    return {"caseId": case_id, "status": "done"}


@broker.task(task_name="case_deep_dive")
async def case_deep_dive_task(case_id: str) -> dict[str, str]:
    """Deferred affiliate/director/individual deep-dive; then queue tree + AI."""
    _ensure_worker_context()
    logger.info("case_deep_dive start: %s", case_id)
    await process_case_deep_dive(case_id)
    await affiliate_tree_task.kiq(case_id)
    await ai_conclusion_task.kiq(case_id)
    logger.info("case_deep_dive queued affiliate_tree + ai_conclusion for %s", case_id)
    return {"caseId": case_id, "status": "done"}


@broker.task(task_name="affiliate_tree")
async def affiliate_tree_task(case_id: str) -> dict[str, str]:
    _ensure_worker_context()
    logger.info("affiliate_tree start: %s", case_id)
    await build_affiliate_tree(case_id)
    logger.info("affiliate_tree done: %s", case_id)
    return {"caseId": case_id, "status": "done"}


@broker.task(task_name="ai_conclusion")
async def ai_conclusion_task(case_id: str) -> dict[str, str]:
    _ensure_worker_context()
    logger.info("ai_conclusion start: %s", case_id)
    await generate_conclusion_for_case(case_id)
    logger.info("ai_conclusion done: %s", case_id)
    return {"caseId": case_id, "status": "done"}


@broker.task(task_name="chat_reply")
async def chat_reply_task(case_id: str, user_message: str) -> dict[str, str]:
    _ensure_worker_context()
    logger.info("chat_reply start: %s", case_id)
    result = await chat_reply_for_case(case_id, user_message)
    logger.info("chat_reply done: %s", case_id)
    return {"caseId": case_id, "status": "done", "messageId": result["message"]["id"]}
