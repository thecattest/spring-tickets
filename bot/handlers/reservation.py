"""
Reservation creation and management handlers.

Handles:
- Forwarded message (create reservation)
- Row input (AWAITING_ROW state)
- Seat input (AWAITING_SEATS state)
- Seat addition menu (SEAT_ADDITION_MENU state)
"""

import logging
from vkbottle.bot import Bot, Message
from vkbottle import VKAPIError

from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage
from bot.utils import db
from bot.utils.seat_parser import parse_seats, SeatParseError
from bot.utils.layout import is_valid_row, is_valid_seat, get_seat_count, get_row_range
from bot.keyboards import seat_addition_menu_keyboard, get_empty_keyboard
from bot.messages import generate_reservation_script
from models.base import SeatStatus

logger = logging.getLogger(__name__)


async def forwarded_message_handler(message: Message):
    """
    Handle forwarded message - create reservation.

    Extracts VK user ID from forwarded message author and creates reservation.
    """
    if not message.fwd_messages:
        return

    # Get VK user ID from forwarded message
    forwarded = message.fwd_messages[0]
    buyer_vk_id = forwarded.from_id

    logger.info(f"Seller {message.from_id} forwarded message from buyer {buyer_vk_id}")

    try:
        # Get or create VK user
        # Note: We don't have display name from forwarded message in this context
        # Will need to fetch from VK API or use ID as placeholder
        vk_user = db.get_or_create_vk_user(buyer_vk_id, f"VK User {buyer_vk_id}")

        # Check if user already has active reservation
        existing = db.get_active_reservation(vk_user.id)

        if existing:
            # Phase 2: show main menu
            await message.answer(
                f"У клиента {vk_user.display_name} уже есть активная бронь (ID: {existing.id}).\n\n"
                "Функция редактирования существующей брони будет доступна в следующей версии."
            )
            return

        # Create new reservation
        seller_id = db.get_default_seller_id()
        reservation = db.create_reservation(vk_user.id, seller_id)

        # Save context to Redis
        storage: RedisStorage = message.ctx_api.state_dispenser
        await storage.update_context(
            message.from_id,
            reservation_id=reservation.id,
            buyer_vk_user_id=vk_user.id,
            buyer_display_name=vk_user.display_name,
        )

        # Transition to AWAITING_ROW
        await message.ctx_api.messages.send(
            peer_id=message.peer_id,
            message=f"Создана новая бронь для {vk_user.display_name} (ID: {reservation.id}).\n\n"
                    f"Введите номер ряда (1-24):",
            random_id=0,
        )

        await storage.set(message.from_id, BotState.AWAITING_ROW)

    except db.DatabaseError as e:
        logger.error(f"Database error creating reservation: {e}")
        await message.answer(
            "Ошибка при создании брони. Попробуйте позже или обратитесь к администратору."
        )


async def awaiting_row_handler(message: Message):
    """
    Handle row input in AWAITING_ROW state.

    Validates row number and transitions to AWAITING_SEATS.
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

    # Save row to context
    storage: RedisStorage = message.state_peer.state_dispenser
    await storage.update_context(message.from_id, current_row=row)

    # Transition to AWAITING_SEATS
    seat_count = get_seat_count(row)
    await message.answer(
        f"Ряд {row} (мест: {seat_count}).\n\n"
        f"Введите номера мест через пробел, запятую или диапазон.\n"
        f"Примеры: '5 6 7' или '5, 6, 7' или '5-7'"
    )

    await storage.set(message.from_id, BotState.AWAITING_SEATS)


async def awaiting_seats_handler(message: Message):
    """
    Handle seat input in AWAITING_SEATS state.

    Parses seats, validates availability, and adds to reservation.
    """
    text = message.text.strip()
    storage: RedisStorage = message.state_peer.state_dispenser
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

    # Check availability
    occupied = []
    for seat in seats:
        assignment = db.get_seat_assignment(row, seat)
        if assignment:
            occupied.append((seat, assignment))

    if occupied:
        # Build error message with details
        error_lines = ["Места уже заняты:"]
        for seat, assignment in occupied:
            if assignment.status == SeatStatus.RESERVED:
                status_text = "Резерв"
                detail = assignment.note or "без комментария"
            else:
                status_text = "Бронь" if assignment.status == SeatStatus.BOOKED else "Оплачено"
                # Get reservation info
                try:
                    res_seats = db.get_reservation_seats(assignment.reservation_id)
                    detail = f"бронь #{assignment.reservation_id}, всего мест: {len(res_seats)}"
                except:
                    detail = f"бронь #{assignment.reservation_id}"

            error_lines.append(f"• Ряд {row}, место {seat} — {status_text} ({detail})")

        error_lines.append("\nВведите другие места:")
        await message.answer("\n".join(error_lines))
        return

    # All seats available - add them
    try:
        seller_id = db.get_default_seller_id()
        assignments = db.add_seats_to_reservation(reservation_id, row, seats, seller_id)

        # Get total seat count for reservation
        all_seats = db.get_reservation_seats(reservation_id)
        total_count = len(all_seats)

        # Success message
        await message.answer(
            f"Добавлено {len(seats)} мест:\n"
            f"Ряд {row}, места: {', '.join(map(str, seats))}\n\n"
            f"Всего в брони: {total_count} мест",
            keyboard=seat_addition_menu_keyboard()
        )

        # Transition to SEAT_ADDITION_MENU
        await storage.set(message.from_id, BotState.SEAT_ADDITION_MENU)

    except db.SeatOccupiedError as e:
        # Race condition - seat was just taken
        await message.answer(
            f"Место ряд {e.row}, место {e.seat} только что было занято.\n"
            f"Попробуйте другие места:"
        )
    except db.DatabaseError as e:
        logger.error(f"Error adding seats: {e}")
        await message.answer(
            "Ошибка при добавлении мест. Попробуйте позже или обратитесь к администратору."
        )


async def seat_addition_menu_handler(message: Message):
    """
    Handle buttons in SEAT_ADDITION_MENU state.

    Buttons:
    - "Добавить еще" - return to AWAITING_ROW
    - "Готово" - generate script and finish
    """
    text = message.text.strip()
    storage: RedisStorage = message.state_peer.state_dispenser
    context = await storage.get_context(message.from_id)

    if text == "Добавить еще":
        # Return to AWAITING_ROW
        await message.answer(
            "Введите номер ряда:",
            keyboard=get_empty_keyboard()
        )
        await storage.set(message.from_id, BotState.AWAITING_ROW)

    elif text == "Готово":
        # Generate script
        reservation_id = context.get("reservation_id")
        buyer_display_name = context.get("buyer_display_name")

        if not reservation_id:
            await message.answer("Ошибка: потерян контекст. Начните заново.")
            await storage.delete(message.from_id)
            return

        try:
            # Get all seats
            seats = db.get_reservation_seats(reservation_id)

            # Generate script
            script = generate_reservation_script(
                buyer_display_name=buyer_display_name,
                seats=seats,
            )

            await message.answer(script, keyboard=get_empty_keyboard())

            # Clear FSM state
            await storage.delete(message.from_id)

        except db.DatabaseError as e:
            logger.error(f"Error generating script: {e}")
            await message.answer(
                "Ошибка при генерации скрипта. Попробуйте позже."
            )

    else:
        # Unknown button
        await message.answer(
            "Выберите действие:",
            keyboard=seat_addition_menu_keyboard()
        )


def register_handlers(bot: Bot):
    """
    Register reservation handlers with the bot.

    Args:
        bot: VKBottle Bot instance
    """
    # Forwarded message (any state except active flows)
    @bot.on.message(func=lambda msg: bool(msg.fwd_messages))
    async def _(message: Message):
        await forwarded_message_handler(message)

    # State-specific handlers
    @bot.on.message(state=BotState.AWAITING_ROW)
    async def _(message: Message):
        await awaiting_row_handler(message)

    @bot.on.message(state=BotState.AWAITING_SEATS)
    async def _(message: Message):
        await awaiting_seats_handler(message)

    @bot.on.message(state=BotState.SEAT_ADDITION_MENU)
    async def _(message: Message):
        await seat_addition_menu_handler(message)

    logger.info("Reservation handlers registered")
