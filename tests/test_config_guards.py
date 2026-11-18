"""
Стражи согласованности compose.yaml и кода: значения, которые по необходимости
записаны в двух местах, не должны разойтись незаметно (ошибка всплыла бы
только при запуске на сервере).
"""

import importlib.util
from pathlib import Path

import pytest
import yaml
from pydantic import SecretStr

from tickets import config

COMPOSE = Path(__file__).resolve().parent.parent / "compose.yaml"
# Сервисы на образе приложения (x-app)
APP_SERVICES = ("db-backup", "migrate", "web", "bot", "cron")


@pytest.fixture(scope="module")
def compose() -> dict:
    # safe_load раскрывает якоря и << — сравниваем то, что увидит Compose
    return yaml.safe_load(COMPOSE.read_text())


def secret_fields() -> set[str]:
    """Имена полей-секретов во всех секциях config.py."""
    return {
        name
        for section in config._Section.__subclasses__()
        for name, field in section.model_fields.items()
        if field.annotation is SecretStr
    }


def test_compose_secrets_match_config(compose):
    declared = set(compose["secrets"])
    fields = secret_fields()
    assert declared - fields == set(), "секрет в compose.yaml без поля в config.py"
    assert fields - declared == set(), "поле-секрет в config.py без секрета в compose.yaml"


def test_secret_files_named_after_secrets(compose):
    # config.py читает /run/secrets/<имя поля>: имя файла на хосте — то же
    for name, spec in compose["secrets"].items():
        assert spec == {"file": f"./secrets/{name}"}, name


def test_services_use_only_declared_secrets(compose):
    declared = set(compose["secrets"])
    for name, service in compose["services"].items():
        assert set(service.get("secrets", [])) <= declared, name


def test_postgres_user_and_db_same_for_server_and_apps(compose):
    services = compose["services"]
    expected = {k: services["postgres"]["environment"][k] for k in ("POSTGRES_USER", "POSTGRES_DB")}
    for name in APP_SERVICES:
        env = services[name]["environment"]
        assert {k: env.get(k) for k in expected} == expected, name


def test_healthchecks_call_existing_modules(compose):
    for name, service in compose["services"].items():
        test = service.get("healthcheck", {}).get("test", [])
        if test[:3] == ["CMD", "python", "-m"]:
            module = test[3]
            assert importlib.util.find_spec(module) is not None, f"{name}: {module}"


def test_tests_use_same_postgres_and_redis_as_compose(compose):
    """Тесты на той же базе, что сервер: образ и локаль (порядок строк) совпадают."""
    import conftest

    services = compose["services"]
    assert services["postgres"]["image"] == conftest.POSTGRES_IMAGE
    initdb_args = services["postgres"]["environment"]["POSTGRES_INITDB_ARGS"]
    assert initdb_args == conftest.POSTGRES_INITDB_ARGS
    assert services["redis"]["image"] == conftest.REDIS_IMAGE
