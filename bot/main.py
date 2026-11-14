"""
Запуск VK-бота: python -m bot (см. bot/__main__.py).

Обычный asyncio: asyncio.run() → run_bot(), инициализация и очистка —
await и try/finally. С vkbottle 4.9 run_polling() — обычная корутина.
"""

import asyncio
import logging
import signal

from vkbottle.bot import Bot

from bot.fsm.storage import RedisStorage
from bot.router import Router
from bot.utils.layout import load_layout
from config import redis_settings, vk_settings
from database import DATABASE_URL_SAFE
from logging_config import setup_logging

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    # FSM-состояния и контекст — в Redis
    redis = redis_settings()
    storage = RedisStorage(
        host=redis.redis_host,
        port=redis.redis_port,
        db=redis.redis_db,
        password=redis.redis_password.get_secret_value(),
    )
    bot = Bot(token=vk_settings().vk_bot_token.get_secret_value(), state_dispenser=storage)

    router = Router(storage=storage)
    router.register_all()
    bot.labeler.load(router.labeler)

    # docker stop / systemctl stop шлют SIGTERM: отменяем эту задачу —
    # await ниже получит CancelledError, и выполнится finally.
    # Ctrl+C (SIGINT) asyncio.run() обрабатывает так же сам.
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)

    try:
        await storage.connect()
        logger.info("Starting polling")
        await bot.run_polling()
        # run_polling() не возвращается; если вернулся — это сбой, а не остановка
        raise RuntimeError("Polling stopped unexpectedly")
    finally:
        await storage.close()
        await bot.api.http_client.close()  # HTTP-сессия к VK API


def main() -> None:
    setup_logging()

    # Ошибки старта и polling не ловим: traceback в лог и код выхода 1 —
    # сбой виден в docker compose ps и перезапускается restart policy
    # Нет токена, пароля Redis и т. п. — ValidationError со списком всех проблем
    vk, redis = vk_settings(), redis_settings()
    load_layout()

    logger.info("Group ID: %s", vk.vk_group_id)
    logger.info("Redis: %s:%s/%s", redis.redis_host, redis.redis_port, redis.redis_db)
    logger.info("Database: %s", DATABASE_URL_SAFE)

    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Запрошенная остановка (Ctrl+C или SIGTERM) — код выхода 0
        logger.info("Bot stopped")
