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
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker


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
    # Quick test: initialize database
    print(f"Connecting to: {DATABASE_URL}")
    init_db()
    print("Database initialized successfully!")
