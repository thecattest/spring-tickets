"""
Команды управления пользователями: /addadmin, /addseller.

Доступны только администраторам. Требуют пересланное сообщение
от VK-пользователя, которого нужно добавить.
"""

import logging
from vkbottle.bot import Message

from bot import texts
from bot.utils import db
from bot.keyboards import commands_keyboard
from models.base import UserRole

logger = logging.getLogger(__name__)


async def _add_user(message: Message, role: UserRole) -> None:
    """Общая логика для /addadmin и /addseller."""
    # Проверяем, что отправитель — админ
    if not db.is_user_admin(message.from_id):
        await message.answer(texts.ERR_ADD_USER_ADMIN_ONLY)
        return

    # Проверяем наличие пересланного сообщения
    if not message.fwd_messages:
        await message.answer(texts.ERR_ADD_USER_NO_FORWARD)
        return

    target_vk_id = message.fwd_messages[0].from_id
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
        if role == UserRole.ADMIN:
            msg = texts.MSG_USER_ADDED_ADMIN
        else:
            msg = texts.MSG_USER_ADDED_SELLER

    await message.answer(
        msg.format(name=display_name, vk_id=target_vk_id),
        keyboard=commands_keyboard(),
    )
    logger.info(f"Admin {message.from_id} added VK {target_vk_id} ({display_name}) as {role.value}")


async def add_admin_handler(message: Message) -> None:
    """/addadmin — добавить администратора."""
    await _add_user(message, UserRole.ADMIN)


async def add_seller_handler(message: Message) -> None:
    """/addseller — добавить билетера."""
    await _add_user(message, UserRole.SELLER)
