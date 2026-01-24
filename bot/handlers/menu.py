"""
Main menu and context switch handlers.

Handles:
- Main menu display and navigation
- Main menu button actions (Добавить, Удалить, Удалить все, Оплата)
- Context switch confirmation when seller switches between clients
"""

import logging
from vkbottle.bot import Bot, Message

from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage
from bot.utils import db
from bot.keyboards import main_menu_keyboard, confirmation_keyboard, get_empty_keyboard, context_switch_keyboard
from bot.messages import format_reservation_seats
from models.base import SeatStatus

logger = logging.getLogger(__name__)


async def show_main_menu(
    message: Message,
    storage: RedisStorage,
    reservation_id: int,
    vk_user_id: int,
    buyer_display_name: str,
):
    """
    Display main menu for existing reservation.

    Args:
        message: VK message
        storage: Redis storage instance
        reservation_id: Reservation ID
        vk_user_id: VK user internal ID (not vk_user_id!)
        buyer_display_name: Display name of buyer
    """
    try:
        # Fetch all seats for reservation
        seats = db.get_reservation_seats(reservation_id)

        # Format seats with status indicators
        formatted_seats = format_reservation_seats(seats)

        # Build main menu message
        menu_text = f"Бронь #{reservation_id} — {buyer_display_name}\n\n{formatted_seats}\n\nВыберите действие:"

        # Send with main menu keyboard
        await message.answer(menu_text, keyboard=main_menu_keyboard())

        # Set FSM state to MAIN_MENU with context
        await storage.set(
            message.from_id,
            BotState.MAIN_MENU,
            reservation_id=reservation_id,
            buyer_vk_user_id=vk_user_id,
            buyer_display_name=buyer_display_name,
            from_main_menu=True,
        )

        logger.info(f"Displayed main menu for reservation {reservation_id}")

    except db.DatabaseError as e:
        logger.error(f"Error displaying main menu: {e}")
        await message.answer(
            "Ошибка при загрузке брони. Попробуйте позже."
        )


async def main_menu_handler(message: Message, storage: RedisStorage):
    """
    Handle button presses in MAIN_MENU state.

    Buttons:
    - "Добавить" - Transition to AWAITING_ROW
    - "Удалить" - Transition to DELETING_ROW
    - "Удалить все" - Transition to CANCEL_CONFIRM
    - "Оплата" - Show placeholder message (Phase 3)

    Args:
        message: VK message
        storage: Redis storage instance
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)
    reservation_id = context.get("reservation_id")
    buyer_display_name = context.get("buyer_display_name")

    if not reservation_id:
        await message.answer("Ошибка: потерян контекст. Начните заново.")
        await storage.delete(message.from_id)
        return

    if text == "Добавить":
        # Transition to AWAITING_ROW (preserve context including from_main_menu=True)
        await message.answer(
            "Введите номер ряда:",
            keyboard=get_empty_keyboard()
        )
        await storage.set(message.from_id, BotState.AWAITING_ROW, **context)

    elif text == "Удалить":
        # Check if reservation has any seats
        try:
            seats = db.get_reservation_seats(reservation_id)

            if not seats:
                await message.answer(
                    "В брони нет мест для удаления.",
                    keyboard=main_menu_keyboard()
                )
                return

            # Transition to DELETING_ROW
            await message.answer(
                "Введите номер ряда для удаления:",
                keyboard=get_empty_keyboard()
            )
            await storage.set(message.from_id, BotState.DELETING_ROW, **context)

        except db.DatabaseError as e:
            logger.error(f"Error checking seats for deletion: {e}")
            await message.answer(
                "Ошибка при проверке мест. Попробуйте позже.",
                keyboard=main_menu_keyboard()
            )

    elif text == "Удалить все":
        # Check if reservation has any seats
        try:
            seats = db.get_reservation_seats(reservation_id)

            if not seats:
                await message.answer(
                    "В брони нет мест.",
                    keyboard=main_menu_keyboard()
                )
                return

            # Count by status
            paid_count = sum(1 for s in seats if s.status == SeatStatus.PAID)
            booked_count = sum(1 for s in seats if s.status == SeatStatus.BOOKED)

            # Build confirmation message
            msg = f"Отменить бронь {buyer_display_name}?\n\nВсего мест: {len(seats)} (бронь: {booked_count}, оплачено: {paid_count})"

            if paid_count > 0:
                msg += f"\n\n⚠️ В брони {paid_count} оплаченных мест. Отмена доступна только админам."

            # Send confirmation
            await message.answer(msg, keyboard=confirmation_keyboard())

            # Transition to CANCEL_CONFIRM
            await storage.set(message.from_id, BotState.CANCEL_CONFIRM, **context)

        except db.DatabaseError as e:
            logger.error(f"Error checking seats for cancellation: {e}")
            await message.answer(
                "Ошибка при проверке мест. Попробуйте позже.",
                keyboard=main_menu_keyboard()
            )

    elif text == "Оплата":
        # Phase 3 placeholder
        await message.answer(
            "Функция оплаты будет доступна в следующей версии",
            keyboard=main_menu_keyboard()
        )

    else:
        # Unknown text - re-show keyboard
        await message.answer(
            "Выберите действие:",
            keyboard=main_menu_keyboard()
        )


async def context_switch_handler(message: Message, storage: RedisStorage):
    """
    Handle context switch confirmation.

    Handles "Да" / "Нет" responses when seller attempts to switch between clients.

    Args:
        message: VK message
        storage: Redis storage instance
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)

    # Extract pending switch info and original state
    pending_buyer_vk_id = context.get("pending_buyer_vk_id")
    pending_buyer_display_name = context.get("pending_buyer_display_name")
    pending_has_reservation = context.get("pending_has_reservation", False)
    pending_reservation_id = context.get("pending_reservation_id")
    original_state = context.get("original_state")
    original_context = context.get("original_context", {})

    if text == "Да":
        # Clear FSM and switch to new client
        await storage.delete(message.from_id)

        if pending_has_reservation:
            # Show main menu for new client's existing reservation
            await show_main_menu(
                message,
                storage,
                pending_reservation_id,
                pending_buyer_vk_id,
                pending_buyer_display_name,
            )
        else:
            # Create new reservation for new client (Phase 1 flow)
            try:
                seller_id = db.get_default_seller_id()
                reservation = db.create_reservation(pending_buyer_vk_id, seller_id)

                await message.answer(
                    f"Создана новая бронь для {pending_buyer_display_name} (ID: {reservation.id}).\n\n"
                    f"Введите номер ряда:",
                    keyboard=get_empty_keyboard()
                )

                await storage.set(
                    message.from_id,
                    BotState.AWAITING_ROW,
                    reservation_id=reservation.id,
                    buyer_vk_user_id=pending_buyer_vk_id,
                    buyer_display_name=pending_buyer_display_name,
                )

            except db.DatabaseError as e:
                logger.error(f"Error creating reservation on context switch: {e}")
                await message.answer(
                    "Ошибка при создании брони. Попробуйте позже."
                )

    elif text == "Нет":
        # Restore previous state and context
        if original_state and original_state != "idle":
            await storage.set(message.from_id, original_state, **original_context)
            await message.answer(
                f"Продолжаем работу с {original_context.get('buyer_display_name', 'предыдущим клиентом')}."
            )
        else:
            # No original state to restore - just clear
            await storage.delete(message.from_id)
            await message.answer("Операция отменена.")

    else:
        # Unknown response - re-show options
        await message.answer(
            "Выберите действие:",
            keyboard=context_switch_keyboard()
        )


def register_handlers(bot: Bot):
    """
    Register menu handlers with the bot.

    Args:
        bot: VKBottle Bot instance
    """
    # Get storage reference from bot
    storage = bot.state_dispenser

    # Wrap handlers with storage access
    async def main_menu_with_storage(message: Message):
        await main_menu_handler(message, storage)

    async def context_switch_with_storage(message: Message):
        await context_switch_handler(message, storage)

    # State-specific handlers
    bot.on.message(state=BotState.MAIN_MENU)(main_menu_with_storage)
    bot.on.message(state=BotState.CONTEXT_SWITCH_CONFIRM)(context_switch_with_storage)

    logger.info("Menu handlers registered")
