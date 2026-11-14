"""
Команды управления пользователями: /addadmin, /addseller, /removeuser, /users.

Доступны только владельцу проекта (OWNER_VK_IDS в конфиге).
"""

import logging

from vkbottle.bot import Message

from tickets.bot import texts
from tickets.bot.keyboards import commands_keyboard
from tickets.bot.utils import db
from tickets.config import vk_settings
from tickets.models.base import UserRole

logger = logging.getLogger(__name__)


async def _add_user(message: Message, role: UserRole) -> None:
    """Общая логика для /addadmin и /addseller."""
    # Проверяем, что отправитель — владелец
    if not vk_settings().is_owner(message.from_id):
        await message.answer(texts.ERR_OWNER_ONLY)
        return

    # Проверяем наличие пересланного или ответного сообщения
    from tickets.bot.handlers.reservation import get_forwarded_or_reply

    forwarded = get_forwarded_or_reply(message)
    if not forwarded:
        await message.answer(texts.ERR_ADD_USER_NO_FORWARD)
        return

    target_vk_id = forwarded.from_id
    if not target_vk_id or target_vk_id <= 0:
        await message.answer(texts.ERR_ADD_USER_NO_FORWARD)
        return

    # Получаем имя через VK API
    try:
        users_info = await message.ctx_api.users.get(user_ids=[target_vk_id])
        if users_info:
            display_name = f"{users_info[0].first_name} {users_info[0].last_name}"
        else:
            display_name = f"User {target_vk_id}"
    except Exception as e:
        logger.warning(f"Failed to fetch VK user info for {target_vk_id}: {e}")
        display_name = f"User {target_vk_id}"

    # Проверяем, есть ли уже такой пользователь
    existing = db.get_app_user_by_vk_id(target_vk_id)

    try:
        db.add_app_user(target_vk_id, display_name, role)
    except Exception as e:
        logger.error(f"Failed to add user {target_vk_id} as {role.value}: {e}")
        await message.answer(texts.ERR_ADD_USER_FAILED)
        return

    if existing and existing.role != role:
        # Роль обновлена
        if role == UserRole.ADMIN:
            msg = texts.MSG_USER_UPDATED_ADMIN
        else:
            msg = texts.MSG_USER_UPDATED_SELLER
    else:
        # Новый пользователь (или роль не изменилась)
        msg = texts.MSG_USER_ADDED_ADMIN if role == UserRole.ADMIN else texts.MSG_USER_ADDED_SELLER

    await message.answer(
        msg.format(name=display_name, vk_id=target_vk_id),
        keyboard=commands_keyboard(),
    )
    logger.info(f"Owner {message.from_id} added VK {target_vk_id} ({display_name}) as {role.value}")


async def add_admin_handler(message: Message) -> None:
    """/addadmin — добавить администратора."""
    await _add_user(message, UserRole.ADMIN)


async def add_seller_handler(message: Message) -> None:
    """/addseller — добавить билетера."""
    await _add_user(message, UserRole.SELLER)


async def remove_user_handler(message: Message) -> None:
    """/removeuser — удалить пользователя из системы."""
    if not vk_settings().is_owner(message.from_id):
        await message.answer(texts.ERR_OWNER_ONLY)
        return

    from tickets.bot.handlers.reservation import get_forwarded_or_reply

    forwarded = get_forwarded_or_reply(message)
    if not forwarded:
        await message.answer(texts.ERR_ADD_USER_NO_FORWARD)
        return

    target_vk_id = forwarded.from_id
    if not target_vk_id or target_vk_id <= 0:
        await message.answer(texts.ERR_ADD_USER_NO_FORWARD)
        return

    if target_vk_id == message.from_id:
        await message.answer(texts.ERR_REMOVE_SELF)
        return

    existing = db.get_app_user_by_vk_id(target_vk_id)
    if not existing:
        await message.answer(texts.ERR_USER_NOT_FOUND)
        return

    try:
        db.deactivate_app_user(target_vk_id)
    except Exception as e:
        logger.error(f"Failed to remove user {target_vk_id}: {e}")
        await message.answer(texts.ERR_ADD_USER_FAILED)
        return

    await message.answer(
        texts.MSG_USER_REMOVED.format(name=existing.display_name, vk_id=target_vk_id),
        keyboard=commands_keyboard(),
    )
    logger.info(f"Owner {message.from_id} removed VK {target_vk_id} ({existing.display_name})")


async def list_users_handler(message: Message) -> None:
    """/users — список всех пользователей системы."""
    if not vk_settings().is_owner(message.from_id):
        await message.answer(texts.ERR_OWNER_ONLY)
        return

    users = db.get_all_app_users()
    if not users:
        await message.answer(texts.MSG_USERS_LIST_EMPTY, keyboard=commands_keyboard())
        return

    lines = []
    for user in users:
        role_label = "админ" if user.role == UserRole.ADMIN else "билетер"
        vk_link = f"vk.com/id{user.vk_user_id}" if user.vk_user_id else "—"
        lines.append(f"• {user.display_name} ({role_label}) — {vk_link}")

    text = texts.MSG_USERS_LIST_HEADER + "\n".join(lines)
    await message.answer(text, keyboard=commands_keyboard())
