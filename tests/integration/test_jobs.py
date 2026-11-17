"""Задачи и бот при отказах — на настоящих Postgres и Redis."""

import pytest


def test_backup_sees_pending_migrations():
    """db-backup делает дамп перед migrate, только если миграции не применены."""
    from alembic import command

    from tickets import db as database
    from tickets.jobs.backup import has_pending_migrations

    assert not has_pending_migrations()  # тестовая база на head
    cfg = database.alembic_config()
    command.downgrade(cfg, "base")
    try:
        assert has_pending_migrations()
    finally:
        command.upgrade(cfg, "head")


@pytest.mark.asyncio
async def test_redis_down_at_runtime_notifies_owner(bot, monkeypatch):
    """
    Redis пропал во время работы: vkbottle читает состояние до выбора
    хендлера, поэтому ответа нет никому (даже на /start), а ошибка уходит
    владельцу. Redis перезапускается сам (restart: unless-stopped, AOF).
    """
    import redis.exceptions
    from vkbottle.exception_factory import ErrorHandler

    from tickets.bot import main

    sent = []

    async def fake_notify(text, **kwargs):
        sent.append(text)

    async def redis_down(*args, **kwargs):
        raise redis.exceptions.ConnectionError("Redis is down")

    monkeypatch.setattr(main, "notify_owner", fake_notify)
    errors = ErrorHandler(redirect_arguments=True)  # как в main.run_bot
    errors.register_undefined_error_handler(main.on_error)
    bot.bot.error_handler = errors
    monkeypatch.setattr(bot.storage.redis, "get", redis_down)

    assert await bot.send(201, "/start") == []
    assert sent == ["⚠️ Ошибка в боте: ConnectionError: Redis is down"]
