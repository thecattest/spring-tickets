"""
Database connection and session factory (PostgreSQL).

Usage:
    from tickets.db import SessionLocal, engine

    with SessionLocal() as session:
        user = session.query(AppUser).filter_by(id=1).first()
        session.commit()

Схемой управляет Alembic (migrations/): `uv run alembic upgrade head`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from tickets.config import PROJECT_ROOT, db_settings

# Параметры подключения — config.DatabaseSettings (POSTGRES_HOST, POSTGRES_PASSWORD, …)
_db = db_settings()
DATABASE_URL = _db.url.render_as_string(hide_password=False)
# Для логов: URL без пароля
DATABASE_URL_SAFE = _db.url.render_as_string(hide_password=True)

# Синхронный engine — Alembic, скрипты, проверки в тестах и (до шага 6 этапа 7)
# веб. Приложение (сервисы, бот, задачи) — через async_engine ниже.
engine = create_engine(
    DATABASE_URL,
    # SQL_ECHO=true — логировать все SQL-запросы (для отладки)
    echo=_db.sql_echo,
    # Проверять соединение перед использованием: переживаем рестарт Postgres
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Don't expire objects after commit
)


# Асинхронный engine — тот же драйвер psycopg 3 в async-режиме (тот же URL).
# Пул соединений привязан к event loop процесса: один loop на процесс (бот,
# задача), в тестах — один loop на сессию pytest.
async_engine = create_async_engine(DATABASE_URL, echo=_db.sql_echo, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    autoflush=False,
    expire_on_commit=False,  # объекты остаются читаемыми после коммита
)


@asynccontextmanager
async def unit_of_work() -> AsyncIterator[AsyncSession]:
    """
    Одна транзакция на операцию — граница, которая коммитит (docs/architecture.md → Транзакции).

        async with unit_of_work() as session:
            reservation = await reservations.create(session, ...)
            await reservations.add_seats(session, reservation.id, ...)
        # здесь — COMMIT; исключение внутри блока — ROLLBACK

    Сервисы (tickets.services) сессию получают аргументом и сами никогда не
    коммитят. Побочные эффекты (сообщения VK, уведомления) — после блока.
    """
    async with AsyncSessionLocal() as session, session.begin():
        yield session


def alembic_config():
    """Конфиг Alembic из [tool.alembic] в pyproject.toml — для вызова из кода."""
    from alembic.config import Config

    return Config(toml_file=PROJECT_ROOT / "pyproject.toml")


def upgrade_db() -> None:
    """То же, что `alembic upgrade head`: применить все миграции."""
    from alembic import command

    command.upgrade(alembic_config(), "head")
