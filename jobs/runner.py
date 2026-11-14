"""
Общая обёртка задачи: логирование, код выхода и уведомление владельцу.

    def main() -> None:
        run_job("backup", backup())   # backup() — async-функция задачи

Успех — код 0. Любое исключение — traceback в лог, сообщение владельцу в VK
и код 1: supercronic и Docker видят сбой, а вы узнаёте о нём без чтения логов.
"""

import asyncio
import logging
import sys
from collections.abc import Coroutine
from typing import Any

from logging_config import setup_logging
from notify import notify_owner

logger = logging.getLogger("jobs")


def run_job(name: str, job: Coroutine[Any, Any, None]) -> None:
    setup_logging()
    logger.info("Job %s started", name)
    try:
        asyncio.run(job)
    except Exception as exc:
        logger.exception("Job %s failed", name)
        asyncio.run(notify_owner(f"⚠️ Задача {name} упала: {type(exc).__name__}: {exc}"))
        sys.exit(1)
    logger.info("Job %s finished", name)
