"""
Database connection and session factory (PostgreSQL).

Usage:
    from tickets.db import SessionLocal, engine

    with SessionLocal() as session:
        user = session.query(AppUser).filter_by(id=1).first()
        session.commit()

Схемой управляет Alembic (migrations/): `uv run alembic upgrade head`.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tickets.config import PROJECT_ROOT, db_settings

# Параметры подключения — config.DatabaseSettings (POSTGRES_HOST, POSTGRES_PASSWORD, …)
_db = db_settings()
DATABASE_URL = _db.url.render_as_string(hide_password=False)
# Для логов: URL без пароля
DATABASE_URL_SAFE = _db.url.render_as_string(hide_password=True)

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


def alembic_config():
    """Конфиг Alembic из [tool.alembic] в pyproject.toml — для вызова из кода."""
    from alembic.config import Config

    return Config(toml_file=PROJECT_ROOT / "pyproject.toml")


def upgrade_db() -> None:
    """То же, что `alembic upgrade head`: применить все миграции."""
    from alembic import command

    command.upgrade(alembic_config(), "head")
