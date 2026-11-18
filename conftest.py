"""
Общая настройка pytest.

Тесты не читают локальные .env и ./secrets/: настройки только из окружения,
которое задаёт этот файл.

Интеграционные тесты (tests/integration/) работают с временными Postgres и
Redis в Docker (testcontainers), а не с базой проекта. Контейнеры стартуют в
pytest_configure — до того, как тестовые модули импортируют tickets.db и
создадут engine; параметры подключения (POSTGRES_*) выставляются в окружение
туда же. Окружение у pydantic-settings важнее .env.

Если в запуске нет интеграционных тестов (`pytest tests/unit`), Docker не нужен:
контейнеры не стартуют, а POSTGRES_HOST указывает в никуда — случайное
обращение к базе из юнит-теста падает, а не уходит в чужую базу.

Фикстуры базы, Redis и бота — в tests/integration/conftest.py.
"""

import os
from pathlib import Path

import pytest
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

# Те же образы и локаль базы, что в Compose (сверяет tests/test_config_guards.py)
POSTGRES_IMAGE = "postgres:18"
POSTGRES_INITDB_ARGS = "--locale-provider=icu --icu-locale=ru-RU"
REDIS_IMAGE = "redis:8-alpine"

INTEGRATION_DIR = Path(__file__).resolve().parent / "tests" / "integration"

# Владелец проекта в тестах (OWNER_VK_IDS)
TEST_OWNER_VK_ID = 900

_postgres: PostgresContainer | None = None
_redis: RedisContainer | None = None


def _isolate_settings() -> None:
    """Без .env и ./secrets/ (иначе, например, SEAT_PRICE из .env меняет суммы)."""
    import tickets.config as app_config

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
        SITE_URL="https://tickets.test",
    )


def _runs_integration(config: pytest.Config) -> bool:
    """Попадают ли в запуск tests/integration (по путям в аргументах pytest)."""
    for arg in config.args:
        path = Path(arg.split("::")[0]).resolve()
        if path.is_relative_to(INTEGRATION_DIR) or INTEGRATION_DIR.is_relative_to(path):
            return True
    return False


def pytest_configure(config: pytest.Config) -> None:
    global _postgres, _redis
    _isolate_settings()
    if not _runs_integration(config):
        # tickets.db создаёт engine при импорте (без подключения) — настройки
        # должны пройти проверку, но вести в никуда
        os.environ.update(
            POSTGRES_HOST="no-database-in-unit-tests.invalid", POSTGRES_PASSWORD="unused"
        )
        return

    _postgres = PostgresContainer(POSTGRES_IMAGE, driver="psycopg").with_env(
        "POSTGRES_INITDB_ARGS", POSTGRES_INITDB_ARGS
    )
    _postgres.start()
    os.environ.update(
        POSTGRES_HOST=_postgres.get_container_host_ip(),
        POSTGRES_PORT=str(_postgres.get_exposed_port(5432)),
        POSTGRES_USER=_postgres.username,
        POSTGRES_PASSWORD=_postgres.password,
        POSTGRES_DB=_postgres.dbname,
    )
    # Redis для FSM: сценарии бота и тесты хранилища
    _redis = RedisContainer(REDIS_IMAGE)
    _redis.start()


def pytest_unconfigure(config: pytest.Config) -> None:
    for container in (_postgres, _redis):
        if container is not None:
            container.stop()


def postgres_container() -> PostgresContainer:
    assert _postgres is not None, "Postgres не запущен: интеграционный тест вне tests/integration?"
    return _postgres


def redis_container() -> RedisContainer:
    assert _redis is not None, "Redis не запущен: интеграционный тест вне tests/integration?"
    return _redis
