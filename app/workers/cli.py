"""Entry point: ``uv run akashicompliance-worker``."""

from __future__ import annotations

import sys

from taskiq.__main__ import main as taskiq_main

from app.core.config import settings


def main() -> None:
    sys.argv = [
        "taskiq",
        "worker",
        "app.workers.broker:broker",
        "app.workers.tasks",
        "--workers",
        str(settings.taskiq_workers),
    ]
    taskiq_main()


if __name__ == "__main__":
    main()
