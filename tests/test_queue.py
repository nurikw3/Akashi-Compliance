from __future__ import annotations

import pytest

from app.services import queue


@pytest.mark.asyncio
async def test_enqueue_inline_when_queue_disabled(monkeypatch):
    async def _inline_backend() -> tuple[str, str | None]:
        return "inline", None

    monkeypatch.setattr(queue, "resolve_queue_backend", _inline_backend)
    result = await queue.enqueue_case_pipeline("test-case")
    assert result["mode"] == "inline"
    assert result["queue"] == "case_pipeline"
    assert "warning" not in result


@pytest.mark.asyncio
async def test_enqueue_inline_fallback_when_no_worker(monkeypatch):
    async def _fallback_backend() -> tuple[str, str | None]:
        return "inline", "TaskIQ worker не обнаружен"

    monkeypatch.setattr(queue, "resolve_queue_backend", _fallback_backend)
    result = await queue.enqueue_case_pipeline("test-case")
    assert result["mode"] == "inline"
    assert result["fallback"] is True
    assert "worker" in result["warning"].lower() or "TaskIQ" in result["warning"]


@pytest.mark.asyncio
async def test_resolve_queue_backend_falls_back_without_heartbeat(monkeypatch):
    monkeypatch.setattr(queue, "_taskiq_configured", lambda: True)
    monkeypatch.setattr(queue, "ping_redis", _async_true)
    monkeypatch.setattr(queue, "worker_heartbeat_ok", _async_false)

    backend, warning = await queue.resolve_queue_backend()
    assert backend == "inline"
    assert warning is not None
    assert "TaskIQ" in warning


async def _async_true() -> bool:
    return True


async def _async_false() -> bool:
    return False
