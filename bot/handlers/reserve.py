"""
Reserve management handlers (admin only).

Handles:
- /Резерв command (entry point, admin check)
- Add reserve flow (RESERVE_ACTION -> RESERVE_ADDING_ROW -> RESERVE_ADDING_SEATS -> RESERVE_COMMENT -> RESERVE_ACTION)
- Remove reserve flow (RESERVE_ACTION -> RESERVE_REMOVING_ROW -> RESERVE_REMOVING_SEATS -> RESERVE_REMOVE_CONFIRM -> RESERVE_ACTION)

Reserves are SeatAssignment rows with status=RESERVED, reservation_id=None, and a mandatory comment (note).
"""

import logging
from vkbottle.bot import Bot, Message

from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage
from bot.utils import db
from bot.utils.seat_parser import parse_seats, SeatParseError
from bot.utils.layout import is_valid_row, is_valid_seat, get_seat_count, get_row_range
from bot.keyboards import (
    reserve_action_keyboard,
    confirmation_keyboard,
    get_empty_keyboard,
)
from bot.messages import format_reserves_list
from bot.utils.formatting import format_seat_ranges
from models.base import SeatStatus

logger = logging.getLogger(__name__)


async def reserve_command_handler(message: Message, storage: RedisStorage):
    """
    /Резерв command handler.

    Checks admin status and shows reserve action keyboard or rejection.
    """
    is_admin = db.is_user_admin(message.from_id)

    if not is_admin:
        await message.answer("Управление резервами доступно только администраторам.")
        return

    # Resolve admin's AppUser.id for DB writes
    app_user = db.get_app_user_by_vk_id(message.from_id)
    if not app_user:
        await message.answer("Ошибка: ваш аккаунт не найден в системе.")
        return

    reserves = db.get_active_reserves()
    reserves_text = format_reserves_list(reserves)

    await message.answer(
        f"{reserves_text}\n\nУправление резервами:",
        keyboard=reserve_action_keyboard()
    )
    await storage.set(message.from_id, BotState.RESERVE_ACTION, admin_user_id=app_user.id)


async def reserve_action_handler(message: Message, storage: RedisStorage):
    """
    Handle reserve action selection (RESERVE_ACTION state).

    Routes to add or remove reserve flow.
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)

    if text == "Добавить":
        await message.answer(
            "Введите номер ряда:",
            keyboard=get_empty_keyboard()
        )
        await storage.set(message.from_id, BotState.RESERVE_ADDING_ROW, **context)

    elif text == "Удалить":
        await message.answer(
            "Введите номер ряда:",
            keyboard=get_empty_keyboard()
        )
        await storage.set(message.from_id, BotState.RESERVE_REMOVING_ROW, **context)

    elif text.startswith("/"):
        # Command entered — clear state and let command handlers process
        await storage.delete(message.from_id)
        # Re-dispatch: manually call the command since state handler consumed the message
        if text in ("/cancel", "/Отмена"):
            from bot.handlers.commands import cancel_handler
            await cancel_handler(message, storage)
        elif text in ("/debtors", "/Должники"):
            from bot.handlers.debtors import _show_debtors
            await _show_debtors(message)
        elif text in ("/reserve", "/Резерв"):
            await reserve_command_handler(message, storage)
        elif text in ("/help", "/Справка"):
            from bot.handlers.commands import help_handler
            await help_handler(message)
        elif text == "/start":
            from bot.handlers.commands import start_handler
            await start_handler(message)

    else:
        await message.answer(
            "Выберите действие:",
            keyboard=reserve_action_keyboard()
        )


async def reserve_adding_row_handler(message: Message, storage: RedisStorage):
    """
    Handle row number input during add reserve (RESERVE_ADDING_ROW state).
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

    # Get existing context to preserve admin_user_id
    context = await storage.get_context(message.from_id)
    context['current_row'] = row

    seat_count = get_seat_count(row)
    await message.answer(
        f"Введите номера мест для резерва (ряд {row}, мест: {seat_count}):"
    )
    await storage.set(message.from_id, BotState.RESERVE_ADDING_SEATS, **context)


async def reserve_adding_seats_handler(message: Message, storage: RedisStorage):
    """
    Handle seat numbers input during add reserve (RESERVE_ADDING_SEATS state).
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)

    row = context.get("current_row")
    if not row:
        await message.answer("Ошибка: потерян контекст. Начните заново с /Резерв.")
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

    # Store seats and prompt for comment
    context['reserve_seats'] = seats
    await message.answer("Введите комментарий для резерва:")
    await storage.set(message.from_id, BotState.RESERVE_COMMENT, **context)


async def reserve_comment_handler(message: Message, storage: RedisStorage):
    """
    Handle comment input during add reserve (RESERVE_COMMENT state).
    """
    comment = message.text.strip()

    if not comment:
        await message.answer("Комментарий обязателен. Введите комментарий:")
        return

    context = await storage.get_context(message.from_id)
    row = context.get("current_row")
    seats = context.get("reserve_seats")
    admin_user_id = context.get("admin_user_id")

    if not all([row, seats, admin_user_id]):
        await message.answer("Ошибка: потерян контекст. Начните заново с /Резерв.")
        await storage.delete(message.from_id)
        return

    try:
        db.add_reserve(row, seats, comment, admin_user_id)

        seats_str = format_seat_ranges(sorted(seats))
        await message.answer(
            f"Резерв создан:\n"
            f"Ряд {row}, места: {seats_str}\n"
            f"Комментарий: {comment}",
            keyboard=reserve_action_keyboard()
        )
        await storage.set(message.from_id, BotState.RESERVE_ACTION, admin_user_id=admin_user_id)

    except db.SeatOccupiedError as e:
        # Show all occupied seats at once
        error_lines = ["Места уже заняты:"]
        for c in e.conflicts:
            if c['status'] == SeatStatus.RESERVED:
                status_text = "Резерв"
                detail = c['note'] or "без комментария"
            else:
                status_text = "Бронь" if c['status'] == SeatStatus.BOOKED else "Оплачено"
                try:
                    res_seats = db.get_reservation_seats(c['reservation_id'])
                    detail = f"бронь #{c['reservation_id']}, всего мест: {len(res_seats)}"
                except Exception:
                    detail = f"бронь #{c['reservation_id']}"
            error_lines.append(f"• Ряд {c['row']}, место {c['seat']} — {status_text} ({detail})")
        error_lines.append("\nВведите другие места:")
        await message.answer("\n".join(error_lines))

        # Re-prompt for seats (go back to RESERVE_ADDING_SEATS)
        # Remove reserve_seats from context so user enters new ones
        context.pop('reserve_seats', None)
        await storage.set(message.from_id, BotState.RESERVE_ADDING_SEATS, **context)

    except db.DatabaseError as e:
        logger.error(f"Error adding reserve: {e}")
        await message.answer(
            f"Ошибка при создании резерва: {e}",
            keyboard=reserve_action_keyboard()
        )
        await storage.set(message.from_id, BotState.RESERVE_ACTION, admin_user_id=admin_user_id)


async def reserve_removing_row_handler(message: Message, storage: RedisStorage):
    """
    Handle row number input during remove reserve (RESERVE_REMOVING_ROW state).
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

    # Get existing context to preserve admin_user_id
    context = await storage.get_context(message.from_id)
    context['current_row'] = row

    seat_count = get_seat_count(row)
    await message.answer(
        f"Введите номера мест для снятия резерва (ряд {row}, мест: {seat_count}):"
    )
    await storage.set(message.from_id, BotState.RESERVE_REMOVING_SEATS, **context)


async def reserve_removing_seats_handler(message: Message, storage: RedisStorage):
    """
    Handle seat numbers input during remove reserve (RESERVE_REMOVING_SEATS state).
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)

    row = context.get("current_row")
    if not row:
        await message.answer("Ошибка: потерян контекст. Начните заново с /Резерв.")
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

    # Store seats and show confirmation
    context['reserve_seats_to_remove'] = seats
    seats_str = format_seat_ranges(sorted(seats))

    await message.answer(
        f"Снять резерв:\n"
        f"Ряд {row}: {seats_str}\n\n"
        f"Подтвердить?",
        keyboard=confirmation_keyboard()
    )
    await storage.set(message.from_id, BotState.RESERVE_REMOVE_CONFIRM, **context)


async def reserve_remove_confirm_handler(message: Message, storage: RedisStorage):
    """
    Handle remove reserve confirmation (RESERVE_REMOVE_CONFIRM state).
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)

    row = context.get("current_row")
    seats = context.get("reserve_seats_to_remove")
    admin_user_id = context.get("admin_user_id")

    if not all([row, seats, admin_user_id]):
        await message.answer("Ошибка: потерян контекст. Начните заново с /Резерв.")
        await storage.delete(message.from_id)
        return

    if text == "Подтвердить":
        try:
            previous_notes = db.release_reserve(row, seats, admin_user_id)

            seats_str = format_seat_ranges(sorted(seats))
            result_text = f"Резерв снят:\nРяд {row}, места: {seats_str}"

            # Show previous notes if any exist
            notes_with_content = [n for n in previous_notes if n.get("note")]
            if notes_with_content:
                result_text += "\n\nПредыдущие комментарии:"
                for note_info in notes_with_content:
                    result_text += f"\n• Место {note_info['seat']}: {note_info['note']}"

            await message.answer(
                result_text,
                keyboard=reserve_action_keyboard()
            )
            await storage.set(message.from_id, BotState.RESERVE_ACTION, admin_user_id=admin_user_id)

        except db.DatabaseError as e:
            logger.error(f"Error releasing reserve: {e}")
            await message.answer(
                f"Ошибка при снятии резерва: {e}",
                keyboard=reserve_action_keyboard()
            )
            await storage.set(message.from_id, BotState.RESERVE_ACTION, admin_user_id=admin_user_id)

    elif text == "Отмена":
        await message.answer(
            "Отменено.",
            keyboard=reserve_action_keyboard()
        )
        await storage.set(message.from_id, BotState.RESERVE_ACTION, admin_user_id=admin_user_id)

    else:
        # Unknown input - re-show keyboard
        await message.answer(
            "Выберите действие:",
            keyboard=confirmation_keyboard()
        )


def register_handlers(bot: Bot):
    """
    Register reserve handlers with the bot.

    Args:
        bot: VKBottle Bot instance
    """
    # Get storage reference from bot
    storage = bot.state_dispenser

    # Wrap handlers with storage access
    async def reserve_command_with_storage(message: Message):
        await reserve_command_handler(message, storage)

    async def reserve_action_with_storage(message: Message):
        await reserve_action_handler(message, storage)

    async def reserve_adding_row_with_storage(message: Message):
        await reserve_adding_row_handler(message, storage)

    async def reserve_adding_seats_with_storage(message: Message):
        await reserve_adding_seats_handler(message, storage)

    async def reserve_comment_with_storage(message: Message):
        await reserve_comment_handler(message, storage)

    async def reserve_removing_row_with_storage(message: Message):
        await reserve_removing_row_handler(message, storage)

    async def reserve_removing_seats_with_storage(message: Message):
        await reserve_removing_seats_handler(message, storage)

    async def reserve_remove_confirm_with_storage(message: Message):
        await reserve_remove_confirm_handler(message, storage)

    # Command handler
    bot.on.message(text=["/reserve", "/Резерв"])(reserve_command_with_storage)

    # State-specific handlers
    bot.on.message(state=BotState.RESERVE_ACTION)(reserve_action_with_storage)
    bot.on.message(state=BotState.RESERVE_ADDING_ROW)(reserve_adding_row_with_storage)
    bot.on.message(state=BotState.RESERVE_ADDING_SEATS)(reserve_adding_seats_with_storage)
    bot.on.message(state=BotState.RESERVE_COMMENT)(reserve_comment_with_storage)
    bot.on.message(state=BotState.RESERVE_REMOVING_ROW)(reserve_removing_row_with_storage)
    bot.on.message(state=BotState.RESERVE_REMOVING_SEATS)(reserve_removing_seats_with_storage)
    bot.on.message(state=BotState.RESERVE_REMOVE_CONFIRM)(reserve_remove_confirm_with_storage)

    logger.info("Reserve handlers registered")
