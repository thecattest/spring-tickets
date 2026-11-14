"""
Зависимости роутов: сессия базы на запрос, вход на страницы админа, IP клиента.

    async def page(session: Session, _: Admin): ...
"""

import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from tickets.config import web_settings
from tickets.db import unit_of_work

COOKIE_NAME = "payments_auth"
COOKIE_MAX_AGE = 24 * 60 * 60  # сутки
LOGIN_PATH = "/payments/login"


async def _session() -> AsyncIterator[AsyncSession]:
    async with unit_of_work() as session:
        yield session


# Транзакция на запрос. scope="function": COMMIT — до отправки ответа (по
# умолчанию FastAPI закрыл бы зависимость уже после ответа, и «сохранено»
# ушло бы клиенту раньше, чем коммит мог упасть)
Session = Annotated[AsyncSession, Depends(_session, scope="function")]


# --- вход на /payments и /concert-day ---------------------------------------


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(web_settings().cookie_secret.get_secret_value())


def password_ok(password: str) -> bool:
    """Сравнение за постоянное время; bytes — compare_digest не принимает не-ASCII str."""
    expected = web_settings().payments_password.get_secret_value()
    return secrets.compare_digest(password.encode(), expected.encode())


def login_token() -> str:
    return _serializer().dumps("authenticated")


def is_admin(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        _serializer().loads(token, max_age=COOKIE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return True


class LoginRequired(Exception):
    """Нет входа — main.py отвечает редиректом на страницу входа."""


async def _require_admin(request: Request) -> None:
    if not is_admin(request):
        raise LoginRequired


Admin = Annotated[None, Depends(_require_admin)]


def client_ip(request: Request) -> str | None:
    """IP клиента: за nginx — X-Real-IP (deploy/tickets-nginx.conf), иначе адрес соединения."""
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)
