"""
Debtors command handler.

Handles:
- /debtors command (entry point, stateless)
- "Обновить" button to refresh debtor list

Both handlers are stateless (no FSM state) -- /debtors is a read-only view.
Seller sees only their own debtors; admin sees all.

Debtor criteria (button view, min_days=0):
- Reservation is ACTIVE
- Has at least one unreleased BOOKED seat
Cron reminders use min_days from config (default 7).
"""

import logging
from vkbottle.bot import Message

from bot import texts
from bot.utils import db
from bot.keyboards import debtors_keyboard
from bot.messages import format_debtors_list
from models.base import UserRole

logger = logging.getLogger(__name__)


async def _show_debtors(message: Message):
    """
    Shared logic for displaying the debtor list.

    Resolves the calling user's identity, determines seller_id based on role,
    queries debtors, and replies with the formatted list.

    Admin sees all debtors (seller_id=None).
    Seller sees only their own (seller_id=app_user.id).

    Args:
        message: VK message object
    """
    app_user = db.get_app_user_by_vk_id(message.from_id)

    if not app_user:
        await message.answer(texts.ERR_NOT_REGISTERED)
        return

    # Admin sees all debtors; seller sees only their own
    if app_user.role == UserRole.ADMIN:
        seller_id = None
    else:
        seller_id = app_user.id

    try:
        debtors = db.get_debtors(seller_id=seller_id)
    except db.DatabaseError as e:
        logger.error(f"Error fetching debtors for user {message.from_id}: {e}")
        await message.answer(texts.ERR_DB_GET_DEBTORS)
        return

    if not debtors:
        await message.answer(texts.MSG_NO_DEBTORS, keyboard=debtors_keyboard())
    else:
        await message.answer(
            format_debtors_list(debtors),
            keyboard=debtors_keyboard()
        )


async def debtors_command_handler(message: Message):
    """
    /debtors command handler.

    Shows the caller's debtor list (filtered by seller role, or all for admin).
    """
    logger.info(f"User {message.from_id} sent /debtors")
    await _show_debtors(message)


async def refresh_debtors_handler(message: Message):
    """
    "Обновить" button handler.

    Re-fetches and re-displays the debtor list with fresh data.
    """
    logger.info(f"User {message.from_id} pressed Обновить (debtors)")
    await _show_debtors(message)
