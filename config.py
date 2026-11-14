"""
Настройки приложения (pydantic-settings). На этапе 7 переезжает в tickets/config.py.

Секции читаются и проверяются по отдельности, при первом обращении:
каждому процессу нужны свои — migrate не нужен токен VK, вебу не нужен Redis,
и секреты монтируются только туда, где используются.

    from config import db_settings
    db_settings().postgres_host

Откуда берутся значения (первое найденное):
  1. переменные окружения (Compose environment:, conftest.py в тестах);
  2. файл .env в корне проекта (локальный запуск через uv run);
  3. файлы секретов: /run/secrets/<имя> (Compose secrets:) или ./secrets/<имя>;
  4. умолчание в коде — только для несекретного и одинакового везде.

Имя переменной = имя поля в верхнем регистре (POSTGRES_PASSWORD),
имя файла секрета = имя поля (postgres_password). Секреты — SecretStr:
в логах и repr видно '**********', значение — .get_secret_value().
"""

from functools import cache
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parent

# Секрет: обязателен и не пустой (пустая строка из .env — тоже ошибка конфигурации)
Secret = Annotated[SecretStr, Field(min_length=1)]

# Несуществующий каталог секретов pydantic-settings считает ошибкой конфигурации
_SECRETS_DIRS = [d for d in (Path("/run/secrets"), PROJECT_ROOT / "secrets") if d.is_dir()]


class _Section(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        secrets_dir=_SECRETS_DIRS or None,
        # В .env и окружении есть переменные других секций и Compose — не ошибка
        extra="ignore",
    )


class DatabaseSettings(_Section):
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "tickets"
    postgres_user: str = "tickets"
    postgres_password: Secret
    sql_echo: bool = False

    @property
    def url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


class RedisSettings(_Section):
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Secret


class VkSettings(_Section):
    vk_bot_token: Secret
    vk_group_id: int
    # Владельцы проекта (не роль в БД): управление пользователями и технические
    # уведомления. В env — через запятую: OWNER_VK_IDS=123,456
    owner_vk_ids: Annotated[list[int], NoDecode]

    @field_validator("owner_vk_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    def is_owner(self, vk_user_id: int) -> bool:
        return vk_user_id in self.owner_vk_ids


class WebSettings(_Section):
    # Без пароля вход проходил бы с пустой строкой, без секрета — cookie подделываемы
    payments_password: Secret
    # Отдельно от пароля: зная пароль, нельзя подделать cookie
    cookie_secret: Secret
    # false — для локального HTTP; за nginx с HTTPS — true (Secure cookie)
    cookie_secure: bool = True


class BackupSettings(_Section):
    backup_dir: Path = PROJECT_ROOT / "backups"
    backup_keep: int = 14
    backup_send_to_vk: bool = True


class AppSettings(_Section):
    """Общие несекретные настройки."""

    log_level: str = "INFO"
    display_tz: ZoneInfo = ZoneInfo("Europe/Moscow")
    seat_price: int = 1500
    debtors_reminder_min_days: int = 7

    @field_validator("display_tz", mode="before")
    @classmethod
    def _zone(cls, value: object) -> object:
        return ZoneInfo(value) if isinstance(value, str) else value


# Одна загрузка на процесс; в тестах кэш сбрасывается: db_settings.cache_clear()
@cache
def db_settings() -> DatabaseSettings:
    return DatabaseSettings()


@cache
def redis_settings() -> RedisSettings:
    return RedisSettings()


@cache
def vk_settings() -> VkSettings:
    return VkSettings()


@cache
def web_settings() -> WebSettings:
    return WebSettings()


@cache
def backup_settings() -> BackupSettings:
    return BackupSettings()


@cache
def app_settings() -> AppSettings:
    return AppSettings()
