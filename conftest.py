"""
Общая настройка pytest: тесты работают с временным Postgres в Docker
(testcontainers), а не с базой проекта. Нужен запущенный Docker.

Контейнер стартует в pytest_configure — до того, как тестовые модули
импортируют database.py и создадут engine; параметры подключения (POSTGRES_*)
выставляются в окружение туда же. Окружение у pydantic-settings важнее .env,
поэтому значения из .env сюда не попадут.

Схема создаётся один раз миграциями (alembic upgrade head) — так тесты
заодно проверяют сами миграции. Перед каждым тестом таблицы очищаются.
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

# Та же мажорная версия, что будет в Compose
POSTGRES_IMAGE = "postgres:18-alpine"
REDIS_IMAGE = "redis:8-alpine"

_container: PostgresContainer | None = None
_redis: RedisContainer | None = None
TEST_DATABASE_URL = ""


# Владелец проекта в тестах (OWNER_VK_IDS)
TEST_OWNER_VK_ID = 900


def _isolate_settings() -> None:
    """
    Тесты не читают локальные .env и ./secrets/: значения только из окружения,
    которое задаёт этот файл (иначе, например, SEAT_PRICE из .env меняет суммы).
    """
    import config as app_config

    for section in app_config._Section.__subclasses__():
        section.model_config["env_file"] = None
        section.model_config["secrets_dir"] = None
    os.environ.update(
        VK_BOT_TOKEN="vk1.a.test",
        VK_GROUP_ID="1",
        OWNER_VK_IDS=str(TEST_OWNER_VK_ID),
        REDIS_PASSWORD="test",
        PAYMENTS_PASSWORD="test",
        COOKIE_SECRET="test",
    )


def pytest_configure(config):
    global _container, _redis, TEST_DATABASE_URL
    _isolate_settings()
    _container = PostgresContainer(POSTGRES_IMAGE, driver="psycopg")
    _container.start()
    TEST_DATABASE_URL = _container.get_connection_url()
    os.environ.update(
        POSTGRES_HOST=_container.get_container_host_ip(),
        POSTGRES_PORT=str(_container.get_exposed_port(5432)),
        POSTGRES_USER=_container.username,
        POSTGRES_PASSWORD=_container.password,
        POSTGRES_DB=_container.dbname,
    )
    # Redis для FSM: сценарии бота и тесты хранилища
    _redis = RedisContainer(REDIS_IMAGE)
    _redis.start()


def pytest_unconfigure(config):
    for container in (_container, _redis):
        if container is not None:
            container.stop()


@pytest_asyncio.fixture
async def redis_storage():
    """FSM-хранилище на временном Redis, пустое перед каждым тестом."""
    from bot.fsm.storage import RedisStorage

    storage = RedisStorage(
        host=_redis.get_container_host_ip(), port=int(_redis.get_exposed_port(6379))
    )
    await storage.connect()
    await storage.redis.flushdb()
    yield storage
    await storage.close()


@pytest_asyncio.fixture
async def bot(redis_storage, monkeypatch):
    """Бот с подменённым VK (bot/tests/scenario.py); выход в сеть запрещён."""
    import aiohttp

    from bot.tests.scenario import BotHarness
    from bot.utils import attachments

    def no_network(*args, **kwargs):
        raise AssertionError("Real HTTP request in test: aiohttp.ClientSession")

    monkeypatch.setattr(aiohttp, "ClientSession", no_network)

    harness = BotHarness(redis_storage)
    # Пересылка чеков админам скачивает фото с CDN VK и загружает заново —
    # в тесте только запоминаем, что и кому переслали бы
    monkeypatch.setattr(attachments, "reupload_attachments", harness.vk.reupload)
    return harness


@pytest.fixture(scope="session")
def migrated_db():
    """Схема временной базы — миграциями, один раз на сессию."""
    import database

    # Защита: если database импортировали раньше, engine смотрит не туда —
    # лучше упасть, чем мигрировать и чистить настоящую базу.
    assert make_url(database.DATABASE_URL) == make_url(TEST_DATABASE_URL), (
        f"Тесты подключены не к временной базе: {database.DATABASE_URL_SAFE}"
    )
    database.upgrade_db()


@pytest.fixture(autouse=True)
def clean_db(migrated_db):
    """Перед каждым тестом — пустые таблицы, счётчики id с 1."""
    import database
    import models  # noqa: F401 — регистрирует все модели в Base.metadata
    from models.base import Base

    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with database.engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield
