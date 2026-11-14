"""Jinja-шаблоны веба и их фильтры."""

from datetime import UTC, datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

from tickets.config import app_settings
from tickets.formatting import format_seat_ranges


def local_dt(value: datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """UTC из базы → часовой пояс концерта (DISPLAY_TZ)."""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(app_settings().display_tz).strftime(fmt)


def rub(value: float | int) -> str:
    """12345.0 → «12 345»."""
    return f"{value:,.0f}".replace(",", " ")


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters.update(local_dt=local_dt, rub=rub, seat_ranges=format_seat_ranges)
