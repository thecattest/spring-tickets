"""Миграции Alembic согласованы с моделями и обратимы."""

from alembic import command
from sqlalchemy import inspect

import database


def test_models_match_migrations():
    """Аналог `alembic check`: в моделях нет изменений без миграции."""
    command.check(database.alembic_config())


def test_downgrade_and_upgrade_again():
    cfg = database.alembic_config()
    command.downgrade(cfg, "base")
    assert inspect(database.engine).get_table_names() == ["alembic_version"]
    command.upgrade(cfg, "head")
    assert "seat_assignments" in inspect(database.engine).get_table_names()
