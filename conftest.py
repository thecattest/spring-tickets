"""
Общая настройка pytest: тесты работают с временным Postgres в Docker
(testcontainers), а не с базой проекта. Нужен запущенный Docker.

Контейнер стартует в pytest_configure — до того, как тестовые модули
импортируют database.py и создадут engine; DATABASE_URL выставляется туда же.
load_dotenv() уже заданные переменные не перезаписывает, поэтому значение
из .env сюда не попадёт.
"""

import os

import pytest
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
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL


def pytest_unconfigure(config):
    if _container is not None:
        _container.stop()


@pytest.fixture(autouse=True)
def clean_db():
    """Перед каждым тестом — пустая база с актуальной схемой."""
    import database
    import models  # noqa: F401 — регистрирует все модели в Base.metadata
    from models.base import Base

    # Защита: если database импортировали раньше, engine смотрит не туда —
    # лучше упасть, чем писать в настоящую базу.
    assert database.DATABASE_URL == TEST_DATABASE_URL, (
        f"Тесты подключены не к временной базе: {database.DATABASE_URL_SAFE}"
    )

    Base.metadata.drop_all(bind=database.engine)
    database.init_db()
    yield
