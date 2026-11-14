#!/usr/bin/env python3
"""
Одноразовый перенос данных из старой SQLite-базы в PostgreSQL (ROADMAP, этап 1).

Использование:
    DATABASE_URL=postgresql+psycopg://... uv run python scripts/migrate_sqlite_to_postgres.py data/tickets.db

Что делает:
1. Создаёт схему в Postgres миграциями (alembic upgrade head). Целевая база
   должна быть пустой (если схема уже есть — без данных).
2. Копирует таблицы в порядке зависимостей одной транзакцией, приводя значения
   к новой схеме: даты — aware UTC (в SQLite лежало наивное UTC), enum — значения
   вместо имён ('PAID' → 'paid'), boolean, JSON, Numeric.
3. Сдвигает sequence первичных ключей, чтобы новые INSERT не упали на дубликате id.
4. Сверяет количество строк в каждой таблице.

Таблица reconcile_checkpoints не переносится (модель удалена).
После переезда скрипт удаляется.
"""

import json
import logging
import sqlite3
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Integer,
    Numeric,
    func,
    select,
    text,
)

import models  # noqa: F401 — регистрирует все модели в Base.metadata
from database import DATABASE_URL_SAFE, engine, upgrade_db
from logging_config import setup_logging
from models.base import Base
from timeutils import ensure_utc

logger = logging.getLogger("migrate_sqlite_to_postgres")

# Порядок вставки — по внешним ключам
TABLE_ORDER = [
    "app_users",
    "vk_users",
    "reservations",
    "seat_assignments",
    "payments",
    "payment_seats",
    "audit_log",
]
SKIPPED_TABLES = ["reconcile_checkpoints"]


def convert(value, column):
    """Значение из SQLite → значение для колонки целевой схемы."""
    if value is None:
        return None
    col_type = column.type
    if isinstance(col_type, DateTime):
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        return ensure_utc(parsed)
    if isinstance(col_type, Enum):
        enum_cls = col_type.enum_class
        if value in enum_cls.__members__:  # старое хранение — имя члена ('PAID')
            return enum_cls[value].value
        return enum_cls(value).value  # уже значение ('paid'); иначе ValueError
    if isinstance(col_type, Boolean):
        return bool(value)
    if isinstance(col_type, JSON):
        return json.loads(value) if isinstance(value, str) else value
    if isinstance(col_type, Numeric):
        return Decimal(str(value))
    if isinstance(col_type, (Integer, BigInteger)):
        return int(value)
    return value


def read_rows(source: sqlite3.Connection, table_name: str) -> tuple[list[str], list[dict]]:
    cursor = source.execute(f'SELECT * FROM "{table_name}"')
    columns = [d[0] for d in cursor.description]
    return columns, [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def main(source_path: Path) -> int:
    setup_logging()
    if not source_path.exists():
        logger.error("SQLite file not found: %s", source_path)
        return 1

    logger.info("Source: %s", source_path)
    logger.info("Target: %s", DATABASE_URL_SAFE)

    upgrade_db()
    with engine.connect() as conn:
        not_empty = [
            name
            for name in TABLE_ORDER
            if conn.execute(select(func.count()).select_from(Base.metadata.tables[name])).scalar()
        ]
    if not_empty:
        logger.error("Target database is not empty: %s", ", ".join(not_empty))
        return 1

    source = sqlite3.connect(source_path)
    source_tables = {
        r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for name in SKIPPED_TABLES:
        if name in source_tables:
            count = source.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
            logger.info("Skipping %s (%d rows): model removed", name, count)

    expected: dict[str, int] = {}
    with engine.begin() as conn:  # одна транзакция: либо всё, либо ничего
        for name in TABLE_ORDER:
            table = Base.metadata.tables[name]
            if name not in source_tables:
                logger.warning("%s: not in source, skipped", name)
                expected[name] = 0
                continue

            columns, rows = read_rows(source, name)
            extra = set(columns) - set(table.columns.keys())
            if extra:
                logger.warning("%s: source columns not in schema, dropped: %s", name, extra)

            target_cols = [c for c in table.columns if c.name in columns]
            payload = [{c.name: convert(row[c.name], c) for c in target_cols} for row in rows]
            if payload:
                conn.execute(table.insert(), payload)
            expected[name] = len(rows)
            logger.info("%s: %d rows copied", name, len(rows))

        # Сдвиг sequence: следующий id = max(id) + 1
        for name in TABLE_ORDER:
            table = Base.metadata.tables[name]
            if "id" not in table.columns or not table.columns["id"].autoincrement:
                continue
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                    f"COALESCE((SELECT max(id) FROM {name}), 1), "
                    f"(SELECT max(id) FROM {name}) IS NOT NULL)"
                )
            )

    source.close()

    ok = True
    with engine.connect() as conn:
        for name in TABLE_ORDER:
            actual = conn.execute(
                select(func.count()).select_from(Base.metadata.tables[name])
            ).scalar()
            status = "OK" if actual == expected[name] else "MISMATCH"
            ok &= actual == expected[name]
            logger.info(
                "check %-18s source=%-5d target=%-5d %s", name, expected[name], actual, status
            )

    if not ok:
        logger.error("Row counts differ")
        return 1
    logger.info("Done")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
