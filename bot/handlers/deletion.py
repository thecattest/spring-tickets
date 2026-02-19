"""
Deletion and cancellation handlers.

Handles:
- Seat deletion flow (DELETING_ROW -> DELETING_SEATS -> DELETION_CONFIRM)
- Reservation cancellation flow (CANCEL_CONFIRM)

Note: Plan 02 menu.py handles button press routing:
- "Удалить" button -> sets state to DELETING_ROW
- "Удалить все" button -> sets state to CANCEL_CONFIRM

This file handles the state handlers that process user input AFTER those transitions.
"""

import logging
from vkbottle.bot import Bot, Message

from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage
from bot.utils import db
from bot.utils.seat_parser import parse_seats, SeatParseError
from bot.utils.layout import is_valid_row, is_valid_seat, get_seat_count, get_row_range
from bot.keyboards import confirmation_keyboard, get_empty_keyboard
from bot.handlers.menu import show_main_menu
from models.base import SeatStatus

logger = logging.getLogger(__name__)


async def deleting_row_handler(message: Message, storage: RedisStorage):
    """
    Handle row number input during deletion.

    Args:
        message: VK message
        storage: Redis storage instance
    """
    text = message.text.strip()

    # Validate row number
    try:
        row = int(text)
    except ValueError:
        min_row, max_row = get_row_range()
        await message.answer(
            f"Неверный формат. Введите номер ряда ({min_row}-{max_row}):"
        )
        return

    if not is_valid_row(row):
        min_row, max_row = get_row_range()
        await message.answer(
            f"Неверный ряд. Допустимые значения: {min_row}-{max_row}. Введите ряд:"
        )
        return

    # Get existing context to preserve it
    context = await storage.get_context(message.from_id)

    # Update context with current_row
    context['current_row'] = row

    # Transition to DELETING_SEATS with updated context
    seat_count = get_seat_count(row)
    await message.answer(
        f"Введите номера мест для удаления (ряд {row}, мест: {seat_count}):"
    )

    await storage.set(message.from_id, BotState.DELETING_SEATS, **context)


async def deleting_seats_handler(message: Message, storage: RedisStorage):
    """
    Handle seat numbers input during deletion.

    Args:
        message: VK message
        storage: Redis storage instance
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)

    row = context.get("current_row")
    reservation_id = context.get("reservation_id")

    if not row or not reservation_id:
        await message.answer("Ошибка: потерян контекст. Начните заново с пересылки сообщения.")
        await storage.delete(message.from_id)
        return

    # Parse seats
    try:
        seats = parse_seats(text)
    except SeatParseError as e:
        await message.answer(f"Ошибка ввода: {e}\n\nПопробуйте снова:")
        return

    # Validate seat numbers for this row
    seat_count = get_seat_count(row)
    invalid_seats = [s for s in seats if not is_valid_seat(row, s)]

    if invalid_seats:
        await message.answer(
            f"Недопустимые номера мест: {', '.join(map(str, invalid_seats))}.\n"
            f"Для ряда {row} доступны места 1-{seat_count}.\n\n"
            f"Введите другие места:"
        )
        return

    # Validate seats belong to this reservation
    try:
        all_reservation_seats = db.get_reservation_seats(reservation_id)

        # Build lookup: (row, seat) -> SeatAssignment
        reservation_seat_map = {
            (s.row_number, s.seat_number): s
            for s in all_reservation_seats
        }

        # Check each selected seat
        not_in_reservation = []
        paid_seats = []

        for seat in seats:
            seat_key = (row, seat)
            if seat_key not in reservation_seat_map:
                not_in_reservation.append(seat)
            else:
                assignment = reservation_seat_map[seat_key]
                if assignment.status == SeatStatus.PAID:
                    paid_seats.append(seat)

        # Error if seats don't belong to reservation
        if not_in_reservation:
            await message.answer(
                f"Места не принадлежат данной брони: {', '.join(map(str, not_in_reservation))}.\n\n"
                f"Введите другие места:"
            )
            return

        # Error if any seats are PAID
        if paid_seats:
            await message.answer(
                f"Места уже оплачены, удалить нельзя: {', '.join(map(str, paid_seats))}.\n\n"
                f"Введите другие места:"
            )
            return

        # All seats are BOOKED and belong to reservation - proceed to confirmation
        context['seats_to_delete'] = seats

        await message.answer(
            f"Удалить места:\nРяд {row}: {', '.join(map(str, seats))}\n",
            keyboard=confirmation_keyboard()
        )

        await storage.set(message.from_id, BotState.DELETION_CONFIRM, **context)

    except db.DatabaseError as e:
        logger.error(f"Error validating seats for deletion: {e}")
        await message.answer(
            "Ошибка при проверке мест. Попробуйте позже."
        )


async def deletion_confirm_handler(message: Message, storage: RedisStorage):
    """
    Handle deletion confirmation.

    Args:
        message: VK message
        storage: Redis storage instance
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)

    reservation_id = context.get("reservation_id")
    buyer_vk_user_id = context.get("buyer_vk_user_id")
    buyer_vk_api_id = context.get("buyer_vk_api_id")
    buyer_display_name = context.get("buyer_display_name")
    row = context.get("current_row")
    seats = context.get("seats_to_delete")

    if not all([reservation_id, row, seats]):
        await message.answer("Ошибка: потерян контекст. Начните заново.")
        await storage.delete(message.from_id)
        return

    if text == "Подтвердить":
        # Release seats
        try:
            seller_id = db.get_seller_id(message.from_id)
            released_count = db.release_seats(reservation_id, row, seats, seller_id)

            await message.answer(
                f"Удалено {released_count} мест.",
                keyboard=get_empty_keyboard()
            )

            # Return to main menu with updated seat list
            await show_main_menu(
                message,
                storage,
                reservation_id,
                buyer_vk_user_id,
                buyer_display_name,
                buyer_vk_api_id,
            )

        except db.DatabaseError as e:
            logger.error(f"Error releasing seats: {e}")
            await message.answer(
                f"Ошибка при удалении мест: {e}",
                keyboard=get_empty_keyboard()
            )

            # Return to main menu anyway
            await show_main_menu(
                message,
                storage,
                reservation_id,
                buyer_vk_user_id,
                buyer_display_name,
                buyer_vk_api_id,
            )

    elif text == "Отмена":
        await message.answer("Отменено.", keyboard=get_empty_keyboard())

        # Return to main menu
        await show_main_menu(
            message,
            storage,
            reservation_id,
            buyer_vk_user_id,
            buyer_display_name,
            buyer_vk_api_id,
        )

    else:
        # Unknown input - re-show keyboard
        await message.answer(
            "Выберите действие:",
            keyboard=confirmation_keyboard()
        )


async def cancel_confirm_handler(message: Message, storage: RedisStorage):
    """
    Handle reservation cancellation confirmation.

    Args:
        message: VK message
        storage: Redis storage instance
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)

    reservation_id = context.get("reservation_id")
    buyer_vk_user_id = context.get("buyer_vk_user_id")
    buyer_vk_api_id = context.get("buyer_vk_api_id")
    buyer_display_name = context.get("buyer_display_name")

    if not reservation_id:
        await message.answer("Ошибка: потерян контекст. Начните заново.")
        await storage.delete(message.from_id)
        return

    if text == "Подтвердить":
        # Check if user is admin
        is_admin = db.is_user_admin(message.from_id)

        try:
            seller_id = db.get_seller_id(message.from_id)
            db.cancel_reservation(reservation_id, seller_id, is_admin)

            await message.answer(
                "Бронь отменена.",
                keyboard=get_empty_keyboard()
            )

            # Clear FSM state (return to IDLE)
            await storage.delete(message.from_id)

        except db.PermissionError:
            await message.answer(
                "В брони есть оплаченные места. Отмена доступна только админам.",
                keyboard=get_empty_keyboard()
            )

            # Return to main menu
            await show_main_menu(
                message,
                storage,
                reservation_id,
                buyer_vk_user_id,
                buyer_display_name,
                buyer_vk_api_id,
            )

        except db.DatabaseError as e:
            logger.error(f"Error cancelling reservation: {e}")
            await message.answer(
                f"Ошибка при отмене брони: {e}",
                keyboard=get_empty_keyboard()
            )

            # Return to main menu
            await show_main_menu(
                message,
                storage,
                reservation_id,
                buyer_vk_user_id,
                buyer_display_name,
                buyer_vk_api_id,
            )

    elif text == "Отмена":
        await message.answer("Отменено.", keyboard=get_empty_keyboard())

        # Return to main menu
        await show_main_menu(
            message,
            storage,
            reservation_id,
            buyer_vk_user_id,
            buyer_display_name,
            buyer_vk_api_id,
        )

    else:
        # Unknown input - re-show keyboard
        await message.answer(
            "Выберите действие:",
            keyboard=confirmation_keyboard()
        )


def register_handlers(bot: Bot):
    """
    Register deletion handlers with the bot.

    Args:
        bot: VKBottle Bot instance
    """
    # Get storage reference from bot
    storage = bot.state_dispenser

    # Wrap handlers with storage access
    async def deleting_row_with_storage(message: Message):
        await deleting_row_handler(message, storage)

    async def deleting_seats_with_storage(message: Message):
        await deleting_seats_handler(message, storage)

    async def deletion_confirm_with_storage(message: Message):
        await deletion_confirm_handler(message, storage)

    async def cancel_confirm_with_storage(message: Message):
        await cancel_confirm_handler(message, storage)

    # State-specific handlers
    bot.on.message(state=BotState.DELETING_ROW)(deleting_row_with_storage)
    bot.on.message(state=BotState.DELETING_SEATS)(deleting_seats_with_storage)
    bot.on.message(state=BotState.DELETION_CONFIRM)(deletion_confirm_with_storage)
    bot.on.message(state=BotState.CANCEL_CONFIRM)(cancel_confirm_with_storage)

    logger.info("Deletion handlers registered")
