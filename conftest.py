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
from sqlalchemy import text
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

# Та же мажорная версия, что будет в Compose
POSTGRES_IMAGE = "postgres:18-alpine"

_container: PostgresContainer | None = None
TEST_DATABASE_URL = ""


def pytest_configure(config):
    global _container, TEST_DATABASE_URL
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


def pytest_unconfigure(config):
    if _container is not None:
        _container.stop()


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
