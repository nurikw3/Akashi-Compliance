"""TaskIQ workers (Redis queue). Run: ``uv run akashicompliance-worker``."""

from app.workers.broker import broker
from app.workers import tasks as _tasks  # noqa: F401 — register @broker.task handlers

__all__ = ["broker"]
