"""
Database connection and session factory.

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
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent

# .env из корня проекта — чтобы DATABASE_URL был одинаковым, кто бы ни
# импортировал database первым (бот, веб, скрипты, python database.py).
# Уже заданные переменные окружения не перезаписываются: значения из Docker
# (--env-file / environment:) и из conftest.py в тестах имеют приоритет.
load_dotenv(PROJECT_ROOT / ".env")


def _resolve_sqlite_path(url: str) -> str:
    """
    Относительный путь SQLite (три слэша) считаем от корня проекта, а не от
    текущей папки: cron запускает скрипты из домашней директории, и
    sqlite:///data/tickets.db иначе указывал бы на ~/data/tickets.db.
    """
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        return url
    db = parsed.database
    if not db or db == ":memory:" or Path(db).is_absolute():
        return url
    return parsed.set(database=str(PROJECT_ROOT / db)).render_as_string(hide_password=False)


# Database URL from environment variable or default SQLite for MVP
DATABASE_URL = _resolve_sqlite_path(os.getenv(
    "DATABASE_URL",
    "sqlite:///tickets.db"
))

# Путь к файлу SQLite (None для in-memory и других СУБД) — например, для бэкапа
_db_name = make_url(DATABASE_URL).database
SQLITE_PATH = (
    Path(_db_name)
    if DATABASE_URL.startswith("sqlite") and _db_name not in (None, "", ":memory:")
    else None
)

# Create engine
# echo=True enables SQL query logging (useful for development)
engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    # SQLite specific settings
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

# Enable foreign keys for SQLite (required for CASCADE deletes)
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Create sessionmaker factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Don't expire objects after commit
)


def init_db() -> None:
    """
    Initialize database: create all tables defined in models.

    Should be called once when setting up the application.
    """
    from models.base import Base
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations() -> None:
    """Apply incremental schema migrations for columns added after initial create_all."""
    migrations = [
        # Block 10: per-payment verification checkbox
        (
            "payments",
            "is_verified",
            "ALTER TABLE payments ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT 0",
        ),
        # Receipt attachments (VK media IDs)
        (
            "payments",
            "receipt_attachments",
            "ALTER TABLE payments ADD COLUMN receipt_attachments TEXT",
        ),
    ]
    with engine.connect() as conn:
        for table, column, ddl in migrations:
            # Check if column already exists (SQLite-compatible)
            result = conn.execute(text(f"PRAGMA table_info({table})"))
            columns = [row[1] for row in result]
            if column not in columns:
                conn.execute(text(ddl))
                conn.commit()


if __name__ == "__main__":
    import logging

    from logging_config import setup_logging

    setup_logging()
    log = logging.getLogger("database")
    log.info("Initializing database: %s", make_url(DATABASE_URL).render_as_string(hide_password=True))
    init_db()
    log.info("Database initialized")
