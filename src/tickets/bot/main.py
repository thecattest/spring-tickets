"""
Запуск VK-бота: python -m tickets.bot (см. src/tickets/bot/__main__.py).

Обычный asyncio: asyncio.run() → run_bot(), инициализация и очистка —
await и try/finally. С vkbottle 4.9 run_polling() — обычная корутина.
"""

import asyncio
import logging
import signal
from typing import Any

from vkbottle import API, BotPolling
from vkbottle.bot import Bot, Message
from vkbottle.exception_factory import ErrorHandler

from tickets.bot import heartbeat, texts, vk
from tickets.bot.fsm.storage import RedisStorage
from tickets.bot.router import Router
from tickets.config import redis_settings, vk_settings
from tickets.db import DATABASE_URL_SAFE
from tickets.hall import load_layout
from tickets.logging import setup_logging
from tickets.notify import notify_owner

logger = logging.getLogger(__name__)


class HeartbeatPolling(BotPolling):
    """
    Long Poll с отметкой после каждого ответа VK. VK отвечает не реже раза в
    wait (25 с), даже без событий, поэтому свежая отметка = запросы к VK
    проходят. Сетевые ошибки до отметки не доходят — она устаревает.
    """

    async def get_event(self, server: dict[str, Any]) -> dict[str, Any]:
        event = await super().get_event(server)
        heartbeat.touch()
        return event


async def on_error(error: Exception, message: Any = None, *args: Any, **kwargs: Any) -> None:
    """
    Необработанная ошибка в хендлере или polling: в лог, владельцу и — если
    упало на сообщении пользователя — ему общий ответ, чтобы он не остался
    без ответа (бизнес-ошибки сценарии обрабатывают сами).
    """
    logger.error("Unhandled bot error", exc_info=error)
    summary = f"{type(error).__name__}: {error}"
    await notify_owner(f"⚠️ Ошибка в боте: {summary}", dedup_key=f"bot:{type(error).__name__}")
    if isinstance(message, Message):
        try:
            await vk.answer(message, texts.ERR_UNEXPECTED)
        except Exception:
            logger.exception("Failed to tell the user about the error")


async def run_bot() -> None:
    # FSM-состояния и контекст — в Redis
    redis = redis_settings()
    storage = RedisStorage(
        host=redis.redis_host,
        port=redis.redis_port,
        db=redis.redis_db,
        password=redis.redis_password.get_secret_value(),
    )
    api = API(vk_settings().vk_bot_token.get_secret_value())
    # redirect_arguments: обработчик получает и сообщение, на котором упал хендлер.
    # Тот же обработчик получают роутер (хендлеры) и polling (без сообщения)
    errors = ErrorHandler(redirect_arguments=True)
    errors.register_undefined_error_handler(on_error)
    bot = Bot(api=api, polling=HeartbeatPolling(api), state_dispenser=storage, error_handler=errors)

    router = Router(storage=storage)
    router.register_all()
    bot.labeler.load(router.labeler)

    # docker stop / systemctl stop шлют SIGTERM: отменяем эту задачу —
    # await ниже получит CancelledError, и выполнится finally.
    # Ctrl+C (SIGINT) asyncio.run() обрабатывает так же сам.
    task = asyncio.current_task()
    assert task is not None  # внутри asyncio.run — всегда есть
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)

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
