"""
Окружение Alembic.

URL и engine — из database.py (тот же DATABASE_URL, что у бота и веба, с .env
и переопределением из окружения). Метаданные — Base.metadata со всеми моделями
и NAMING_CONVENTION, чтобы autogenerate видел имена ограничений.
"""

import logging

from alembic import context

import tickets.models  # noqa: F401 — регистрирует все модели в Base.metadata
from tickets.db import DATABASE_URL, DATABASE_URL_SAFE, engine
from tickets.logging import setup_logging
from tickets.models.base import Base

logger = logging.getLogger("alembic.env")
target_metadata = Base.metadata

# basicConfig не перенастраивает уже настроенное логирование,
# поэтому вызов безопасен и при запуске из кода (тесты, скрипты)
setup_logging()

COMPARE_OPTIONS = {
    "target_metadata": target_metadata,
    "compare_type": True,
    "compare_server_default": True,
}


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` — вывести SQL без подключения к базе."""
    context.configure(
        url=DATABASE_URL,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **COMPARE_OPTIONS,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    logger.info("Database: %s", DATABASE_URL_SAFE)
    with engine.connect() as connection:
        context.configure(connection=connection, **COMPARE_OPTIONS)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
