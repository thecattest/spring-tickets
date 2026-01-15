"""
Database connection and session factory.

Usage:
    from database import get_session, engine
    
    # Using context manager (recommended)
    with get_session() as session:
        user = session.query(AppUser).filter_by(id=1).first()
        session.commit()
    
    # Or manually
    session = SessionLocal()
    try:
        user = session.query(AppUser).filter_by(id=1).first()
        session.commit()
    finally:
        session.close()
    
    # Initialize database (create all tables)
    from models.base import Base
    Base.metadata.create_all(bind=engine)
"""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session


# Database URL from environment variable or default SQLite for MVP
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///tickets.db"
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


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    
    Automatically handles commit/rollback and session cleanup.
    
    Example:
        with get_session() as session:
            user = session.query(AppUser).filter_by(id=1).first()
            session.commit()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """
    Initialize database: create all tables defined in models.
    
    Should be called once when setting up the application.
    """
    from models.base import Base
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    # Quick test: initialize database
    print(f"Connecting to: {DATABASE_URL}")
    init_db()
    print("Database initialized successfully!")
