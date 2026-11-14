"""
Database connection and session factory (PostgreSQL).

Usage:
    from database import SessionLocal, engine

    with SessionLocal() as session:
        user = session.query(AppUser).filter_by(id=1).first()
        session.commit()

Схемой управляет Alembic (migrations/): `uv run alembic upgrade head`.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent

# .env из корня проекта — чтобы DATABASE_URL был одинаковым, кто бы ни
# импортировал database первым (бот, веб, скрипты, alembic).
# Уже заданные переменные окружения не перезаписываются: значения из Docker
# (--env-file / environment:) и из conftest.py в тестах имеют приоритет.
load_dotenv(PROJECT_ROOT / ".env")

# Например: postgresql+psycopg://tickets:password@localhost:5432/tickets
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set (e.g. postgresql+psycopg://user:password@localhost:5432/tickets)"
    )

# Для логов: URL без пароля
DATABASE_URL_SAFE = make_url(DATABASE_URL).render_as_string(hide_password=True)

engine = create_engine(
    DATABASE_URL,
    # SQL_ECHO=true — логировать все SQL-запросы (для отладки)
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    # Проверять соединение перед использованием: переживаем рестарт Postgres
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Don't expire objects after commit
)


def alembic_config():
    """Конфиг Alembic из [tool.alembic] в pyproject.toml — для вызова из кода."""
    from alembic.config import Config

    return Config(toml_file=PROJECT_ROOT / "pyproject.toml")


def upgrade_db() -> None:
    """То же, что `alembic upgrade head`: применить все миграции."""
    from alembic import command

    command.upgrade(alembic_config(), "head")
