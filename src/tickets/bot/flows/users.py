"""Пользователи системы (только владелец): /addadmin, /addseller, /removeuser, /users."""

import logging

from vkbottle.bot import Message

from tickets.bot import auth, texts, vk
from tickets.bot.keyboards import commands_keyboard
from tickets.db import unit_of_work
from tickets.models.base import UserRole
from tickets.services import users
from tickets.services.errors import ServiceError

logger = logging.getLogger(__name__)


def _target_vk_id(message: Message) -> int | None:
    """Кого добавить / удалить: автор пересланного сообщения или того, на которое ответили."""
    forwarded = vk.forwarded_or_reply(message)
    vk_id = getattr(forwarded, "from_id", None)
    return vk_id if vk_id and vk_id > 0 else None


async def _add(message: Message, role: UserRole) -> None:
    target = _target_vk_id(message)
    if target is None:
        await vk.answer(message, texts.ERR_ADD_USER_NO_FORWARD)
        return
    try:
        found = await vk.full_name(message.ctx_api, target)
    except Exception as e:
        logger.warning("Failed to fetch VK user %s: %s", target, e)
        found = None
    name = found[1] if found else f"User {target}"

    try:
        async with unit_of_work() as session:
            existing = await users.get_active_app_user(session, target)
            role_changed = existing is not None and existing.role != role
            await users.add_app_user(session, target, name, role, by_vk_id=message.from_id)
    except ServiceError as e:
        logger.error("Failed to add user %s as %s: %s", target, role.value, e)
        await vk.answer(message, texts.ERR_ADD_USER_FAILED)
        return

    if role == UserRole.ADMIN:
        template = texts.MSG_USER_UPDATED_ADMIN if role_changed else texts.MSG_USER_ADDED_ADMIN
    else:
        template = texts.MSG_USER_UPDATED_SELLER if role_changed else texts.MSG_USER_ADDED_SELLER
    await vk.answer(message, template.format(name=name, vk_id=target), keyboard=commands_keyboard())
    logger.info("Owner %s set VK %s as %s", message.from_id, target, role.value)


@auth.owner_only
async def on_add_admin(message: Message) -> None:
    await _add(message, UserRole.ADMIN)


@auth.owner_only
async def on_add_seller(message: Message) -> None:
    await _add(message, UserRole.SELLER)


@auth.owner_only
async def on_remove(message: Message) -> None:
    target = _target_vk_id(message)
    if target is None:
        await vk.answer(message, texts.ERR_ADD_USER_NO_FORWARD)
        return
    if target == message.from_id:
        await vk.answer(message, texts.ERR_REMOVE_SELF)
        return
    try:
        async with unit_of_work() as session:
            existing = await users.get_active_app_user(session, target)
            if existing is not None:
                await users.deactivate_app_user(session, target, by_vk_id=message.from_id)
    except ServiceError as e:
        logger.error("Failed to remove user %s: %s", target, e)
        await vk.answer(message, texts.ERR_ADD_USER_FAILED)
        return
    if existing is None:
        await vk.answer(message, texts.ERR_USER_NOT_FOUND)
        return
    await vk.answer(
        message,
        texts.MSG_USER_REMOVED.format(name=existing.display_name, vk_id=target),
        keyboard=commands_keyboard(),
    )


@auth.owner_only
async def on_list(message: Message) -> None:
    async with unit_of_work() as session:
        all_users = await users.active_users(session)
    if not all_users:
        await vk.answer(message, texts.MSG_USERS_LIST_EMPTY, keyboard=commands_keyboard())
        return
    lines = [
        f"• {u.display_name} ({'админ' if u.role == UserRole.ADMIN else 'билетер'}) — "
        f"{f'vk.com/id{u.vk_user_id}' if u.vk_user_id else '—'}"
        for u in all_users
    ]
    await vk.answer(
        message, texts.MSG_USERS_LIST_HEADER + "\n".join(lines), keyboard=commands_keyboard()
    )
