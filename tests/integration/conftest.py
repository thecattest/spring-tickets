"""
Фикстуры интеграционных тестов: временные Postgres и Redis (контейнеры
поднимает корневой conftest.py), бот с подменённым VK.

Схема создаётся один раз миграциями (alembic upgrade head) — так тесты заодно
проверяют сами миграции. Перед каждым тестом таблицы очищаются (TRUNCATE).

Почему не откат транзакции на тест: код сам коммитит через unit_of_work(), а
часть тестов проверяет именно взаимодействие транзакций (две оплаты одной
брони в двух соединениях, гонка за место) — внутри одной обёрточной транзакции
этого не воспроизвести. TRUNCATE десятка пустых таблиц занимает миллисекунды.
"""

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url

from conftest import postgres_container, redis_container


@pytest.fixture(scope="session")
def migrated_db():
    """Схема временной базы — миграциями, один раз на сессию."""
    from tickets import db as database

    # Защита: если tickets.db импортировали раньше, чем корневой conftest
    # выставил POSTGRES_*, engine смотрит не туда — лучше упасть, чем
    # мигрировать и чистить настоящую базу.
    expected = make_url(postgres_container().get_connection_url())
    assert make_url(database.DATABASE_URL) == expected, (
        f"Тесты подключены не к временной базе: {database.DATABASE_URL_SAFE}"
    )
    database.upgrade_db()


@pytest.fixture(autouse=True)
def clean_db(migrated_db):
    """Перед каждым тестом — пустые таблицы, счётчики id с 1."""
    import tickets.models  # noqa: F401 — регистрирует все модели в Base.metadata
    from tickets import db as database
    from tickets.models.base import Base

    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with database.engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture
async def redis_storage():
    """FSM-хранилище на временном Redis, пустое перед каждым тестом."""
    from tickets.bot.fsm.storage import RedisStorage

    redis = redis_container()
    storage = RedisStorage(
        host=redis.get_container_host_ip(), port=int(redis.get_exposed_port(6379))
    )
    await storage.connect()
    await storage.redis.flushdb()
    yield storage
    await storage.close()


@pytest_asyncio.fixture
async def bot(redis_storage, monkeypatch):
    """Бот с подменённым VK (tests/integration/scenario.py); выход в сеть запрещён."""
    import aiohttp

    from tests.integration.scenario import BotHarness
    from tickets.bot.utils import attachments

    def no_network(*args, **kwargs):
        raise AssertionError("Real HTTP request in test: aiohttp.ClientSession")

    monkeypatch.setattr(aiohttp, "ClientSession", no_network)

    harness = BotHarness(redis_storage)
    # Пересылка чеков админам скачивает фото с CDN VK и загружает заново —
    # в тесте только запоминаем, что и кому переслали бы
    monkeypatch.setattr(attachments, "reupload_attachments", harness.vk.reupload)
    return harness
