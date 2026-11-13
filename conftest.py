"""
Общая настройка pytest: все тесты работают с временной базой, а не с базой проекта.

DATABASE_URL выставляется при импорте этого файла — pytest загружает conftest.py
раньше тестовых модулей, то есть до того, как они импортируют database.py и
создадут engine. load_dotenv() уже заданные переменные не перезаписывает,
поэтому значение из .env сюда не попадёт.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP_DIR = tempfile.mkdtemp(prefix="tickets-tests-")
TEST_DATABASE_URL = f"sqlite:///{Path(_TMP_DIR) / 'test.db'}"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


@pytest.fixture(autouse=True)
def clean_db():
    """Перед каждым тестом — пустая база с актуальной схемой."""
    import database
    import models  # noqa: F401 — регистрирует все модели в Base.metadata
    from models.base import Base

    # Защита: если database импортировали раньше conftest, engine смотрит
    # не туда — лучше упасть, чем писать в настоящую базу.
    assert database.DATABASE_URL == TEST_DATABASE_URL, (
        f"Тесты подключены не к временной базе: {database.DATABASE_URL}"
    )

    Base.metadata.drop_all(bind=database.engine)
    database.init_db()
    yield


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP_DIR, ignore_errors=True)
