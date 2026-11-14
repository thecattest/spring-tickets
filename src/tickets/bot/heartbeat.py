"""
Отметка «polling бота жив» и её проверка для healthcheck Docker.

Бот (HeartbeatPolling в tickets.bot.main) обновляет время файла после каждого
ответа Long Poll; VK отвечает не реже раза в 25 с, даже без событий.

    python -m tickets.bot.heartbeat    # код 0 — отметка свежая, 1 — нет

Это и есть healthcheck сервиса bot в compose.yaml: путь и порог живут только
здесь. Модуль лёгкий (без vkbottle) — проверка запускается каждые 30 с.
"""

import sys
import time
from pathlib import Path

HEARTBEAT_FILE = Path("/tmp/bot-heartbeat")
# Старше — polling не получает ответов VK (с запасом на несколько циклов по 25 с)
MAX_AGE_SECONDS = 120


def touch() -> None:
    HEARTBEAT_FILE.touch()


def is_fresh() -> bool:
    try:
        age = time.time() - HEARTBEAT_FILE.stat().st_mtime
    except FileNotFoundError:
        return False  # ещё не было ни одного ответа VK
    return age <= MAX_AGE_SECONDS


if __name__ == "__main__":
    sys.exit(0 if is_fresh() else 1)
