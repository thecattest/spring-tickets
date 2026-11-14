"""
Время в проекте: везде aware-datetime в UTC.

В БД — timestamptz; в часовой пояс показа (DISPLAY_TZ) переводим только при выводе.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Текущее время, aware, UTC. Вместо устаревшего datetime.utcnow()."""
    return datetime.now(UTC)


def from_unix(ts: int | float) -> datetime:
    """Unix-время (например, date из VK API) → aware UTC."""
    return datetime.fromtimestamp(ts, UTC)


def ensure_utc(value: datetime) -> datetime:
    """Наивное значение считаем UTC (старые данные, старые FSM-контексты), aware — переводим в UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
