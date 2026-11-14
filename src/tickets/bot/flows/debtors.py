"""«Должники» и «Обновить»: админ видит всех, билетёр — только свои брони."""

import logging

from vkbottle.bot import Message

from tickets.bot import auth, texts, vk
from tickets.bot.keyboards import debtors_keyboard
from tickets.bot.messages import format_debtors_list
from tickets.db import unit_of_work
from tickets.models.base import UserRole
from tickets.services import reports
from tickets.services.errors import ServiceError

logger = logging.getLogger(__name__)


async def on_debtors(message: Message) -> None:
    user = await auth.current_user(message)
    if user is None:
        await vk.answer(message, texts.ERR_NOT_REGISTERED)
        return
    seller_id = None if user.role == UserRole.ADMIN else user.id
    try:
        async with unit_of_work() as session:
            debtors = await reports.debtors(session, seller_id=seller_id)
    except ServiceError as e:
        logger.error("Error fetching debtors for %s: %s", message.from_id, e)
        await vk.answer(message, texts.ERR_DB_GET_DEBTORS)
        return
    text = format_debtors_list(debtors) if debtors else texts.MSG_NO_DEBTORS
    await vk.answer(message, text, keyboard=debtors_keyboard())
