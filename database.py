"""
Database connection and session factory (PostgreSQL).

Usage:
    from database import SessionLocal, engine

    with SessionLocal() as session:
        user = session.query(AppUser).filter_by(id=1).first()
        session.commit()

    # Initialize database (create all tables)
    from database import init_db
    init_db()
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent

# .env из корня проекта — чтобы DATABASE_URL был одинаковым, кто бы ни
# импортировал database первым (бот, веб, скрипты, python database.py).
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


def init_db() -> None:
    """
    Create all tables defined in models (until Alembic takes over — ROADMAP stage 2).
    """
    import models  # noqa: F401 — регистрирует все модели в Base.metadata
    from models.base import Base

    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    import logging

    from logging_config import setup_logging

    setup_logging()
    log = logging.getLogger("database")
    log.info("Initializing database: %s", DATABASE_URL_SAFE)
    init_db()
    log.info("Database initialized")
