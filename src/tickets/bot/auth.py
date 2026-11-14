"""
Права в боте: роли из базы (билетёр, админ) и владельцы проекта из настроек.

    @requires_admin(denied=texts.ERR_RESERVE_ADMIN_ONLY)
    async def reserve_command(message, storage): ...

    @owner_only
    async def add_admin(message): ...

Хендлеры состояний защищает роутер по FSM_CONFIG[state].auth_guard (guard_state).
"""

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from vkbottle.bot import Message

from tickets.bot import texts, vk
from tickets.bot.fsm.storage import RedisStorage
from tickets.config import vk_settings
from tickets.db import unit_of_work
from tickets.models.base import UserRole
from tickets.models.user import AppUser
from tickets.services import users

logger = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[None]]


async def current_user(message: Message) -> AppUser | None:
    """Активный пользователь системы, написавший сообщение, или None."""
    async with unit_of_work() as session:
        return await users.get_active_app_user(session, message.from_id)


async def role(message: Message) -> UserRole | None:
    user = await current_user(message)
    return None if user is None else user.role


def requires_admin(denied: str) -> Callable[[Handler], Handler]:
    """Только админ; иначе — ответ denied (состояние не трогаем)."""

    def decorator(handler: Handler) -> Handler:
        @functools.wraps(handler)
        async def wrapped(message: Message, *args, **kwargs):
            if await role(message) != UserRole.ADMIN:
                await vk.answer(message, denied)
                return
            await handler(message, *args, **kwargs)

        return wrapped

    return decorator


def requires_registered(denied: str = texts.ERR_NOT_REGISTERED) -> Callable[[Handler], Handler]:
    """Билетёр или админ; иначе — ответ denied."""

    def decorator(handler: Handler) -> Handler:
        @functools.wraps(handler)
        async def wrapped(message: Message, *args, **kwargs):
            if await role(message) is None:
                await vk.answer(message, denied)
                return
            await handler(message, *args, **kwargs)

        return wrapped

    return decorator


def owner_only(handler: Handler) -> Handler:
    """Только владелец проекта (OWNER_VK_IDS), не роль в базе."""

    @functools.wraps(handler)
    async def wrapped(message: Message, *args, **kwargs):
        if not vk_settings().is_owner(message.from_id):
            await vk.answer(message, texts.ERR_OWNER_ONLY)
            return
        await handler(message, *args, **kwargs)

    return wrapped


def guard_state(
    handler: Handler, guard: Literal["any", "seller", "admin"], storage: RedisStorage
) -> Callable[[Message], Awaitable[None]]:
    """
    Хендлер состояния FSM с проверкой роли (guard из FSM_CONFIG) и хранилищем.
    Нет прав — ответ и сброс состояния: пользователь оказался в чужом сценарии
    (например, роль сняли посреди диалога).
    """

    async def wrapped(message: Message) -> None:
        if guard != "any":
            current = await role(message)
            if current is None:
                await vk.answer(message, "У вас нет доступа к этой функции.")
                await storage.reset(message.from_id)
                return
            if guard == "admin" and current != UserRole.ADMIN:
                await vk.answer(message, "Эта функция доступна только администраторам.")
                await storage.reset(message.from_id)
                return
        await handler(message, storage)

    wrapped.__name__ = f"{handler.__name__}_guarded"
    return wrapped
