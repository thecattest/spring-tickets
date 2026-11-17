"""Миграции Alembic согласованы с моделями и обратимы."""

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from tickets import db as database
from tickets.models.base import Base

REFERENCE_DB = "reference_create_all"

# Описание схемы из системных каталогов. Определения Postgres выдаёт в
# нормализованном виде, поэтому их можно сравнивать как строки — неважно,
# как ограничение записано в модели или миграции.
SCHEMA_QUERIES = {
    "tables": """
        SELECT c.relname, obj_description(c.oid, 'pg_class')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
    """,
    # Без порядка колонок: add_column дописывает в конец, create_all — по модели
    "columns": """
        SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
               a.attnotnull, pg_get_expr(d.adbin, d.adrelid),
               col_description(c.oid, a.attnum)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE n.nspname = 'public' AND c.relkind = 'r'
          AND a.attnum > 0 AND NOT a.attisdropped
    """,
    # CHECK, UNIQUE, FOREIGN KEY, PRIMARY KEY
    "constraints": """
        SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE connamespace = 'public'::regnamespace
    """,
    # Включая условие WHERE частичных индексов
    "indexes": """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes WHERE schemaname = 'public'
    """,
}


def schema_snapshot(engine) -> dict[str, set[tuple]]:
    with engine.connect() as conn:
        return {
            kind: {
                tuple(row)
                for row in conn.execute(text(sql))
                # Служебная таблица Alembic есть только в мигрированной базе
                if "alembic_version" not in row[0]
            }
            for kind, sql in SCHEMA_QUERIES.items()
        }


@pytest.fixture(scope="module")
def reference_engine():
    """Соседняя база в том же контейнере со схемой из create_all() — эталон моделей."""
    with database.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {REFERENCE_DB}"))
        conn.execute(text(f"CREATE DATABASE {REFERENCE_DB}"))
    engine = create_engine(make_url(database.DATABASE_URL).set(database=REFERENCE_DB))
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_migrations_produce_model_schema(reference_engine):
    """
    Схема после миграций совпадает со схемой из моделей до символа.

    Ловит то, что не видят autogenerate и `alembic check`: CHECK-ограничения
    (в том числе значения enum), условия частичных индексов, комментарии.
    """
    migrated = schema_snapshot(database.engine)
    expected = schema_snapshot(reference_engine)

    diff = []
    for kind in SCHEMA_QUERIES:
        diff += [f"  только в миграциях   {kind}: {r}" for r in migrated[kind] - expected[kind]]
        diff += [f"  только в моделях     {kind}: {r}" for r in expected[kind] - migrated[kind]]
    assert not diff, "Схема из миграций расходится с моделями:\n" + "\n".join(sorted(diff))


def test_models_match_migrations():
    """Аналог `alembic check`: в моделях нет изменений без миграции."""
    command.check(database.alembic_config())


def test_downgrade_and_upgrade_again():
    cfg = database.alembic_config()
    command.downgrade(cfg, "base")
    assert inspect(database.engine).get_table_names() == ["alembic_version"]
    command.upgrade(cfg, "head")
    assert "seat_assignments" in inspect(database.engine).get_table_names()
