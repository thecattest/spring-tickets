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
from bot.keyboards import seat_addition_menu_keyboard, get_empty_keyboard, context_switch_keyboard, main_menu_keyboard
from bot.messages import generate_reservation_script
from models.base import SeatStatus
from bot.handlers.menu import show_main_menu

logger = logging.getLogger(__name__)


def forwarded_has_receipt_attachment(forwarded) -> bool:
    """Check if forwarded message has photo or document attachment (receipt indicator)."""
    if not hasattr(forwarded, 'attachments') or not forwarded.attachments:
        return False
    for att in forwarded.attachments:
        if att.photo is not None or att.doc is not None:
            return True
    return False


async def forwarded_message_handler(message: Message, storage: RedisStorage):
    """
    Handle forwarded message - create or show existing reservation.

    Handles three scenarios:
    1. Seller is IDLE, client has NO reservation -> create new reservation
    2. Seller is IDLE, client HAS active reservation -> show main menu
    3. Seller is NOT IDLE (working with another client) -> context switch confirmation

    For MAIN_MENU state, receipt forwards (photo/doc) are routed to payment flow.
    Plain text forwards in MAIN_MENU re-show the main menu (same client) or offer
    context switch (different client).

    Args:
        message: VK message
        storage: Redis storage instance
    """
    if not message.fwd_messages:
        return

    # Get VK user ID from forwarded message
    forwarded = message.fwd_messages[0]
    buyer_vk_id = forwarded.from_id
    is_receipt = forwarded_has_receipt_attachment(forwarded)

    logger.info(f"Seller {message.from_id} forwarded message from buyer {buyer_vk_id} (is_receipt={is_receipt})")

    # Fetch VK user name via VK API (single location)
    try:
        vk_users = await message.ctx_api.users.get(user_ids=[buyer_vk_id])
        if vk_users:
            vk_info = vk_users[0]
            display_name = f"{vk_info.first_name} {vk_info.last_name}"
        else:
            display_name = f"VK User {buyer_vk_id}"
    except Exception as e:
        logger.warning(f"Failed to fetch VK user info for {buyer_vk_id}: {e}")
        display_name = f"VK User {buyer_vk_id}"

    # Check current FSM state
    state_peer = await storage.get(message.from_id)
    current_state = state_peer.state if state_peer else "idle"

    # Scenario 3: Seller is NOT IDLE (working with another client)
    if current_state != "idle":
        current_context = state_peer.payload
        current_buyer_vk_api_id = current_context.get("buyer_vk_api_id")

        # MAIN_MENU state handling
        if current_state == str(BotState.MAIN_MENU):
            if buyer_vk_id == current_buyer_vk_api_id:
                # Same client
                if is_receipt:
                    # Receipt from same client -> payment flow
                    from bot.handlers.payment import start_payment_flow
                    reservation_id = current_context.get("reservation_id")
                    vk_message_ts = None
                    if forwarded.date:
                        from datetime import datetime as dt
                        vk_message_ts = dt.utcfromtimestamp(forwarded.date)
                    await start_payment_flow(
                        message, storage, reservation_id, display_name,
                        vk_message_url=None,
                        vk_message_ts=vk_message_ts,
                    )
                else:
                    # Plain text forward from same client -> re-show main menu
                    reservation_id = current_context.get("reservation_id")
                    buyer_vk_user_id = current_context.get("buyer_vk_user_id")
                    await show_main_menu(
                        message, storage, reservation_id,
                        buyer_vk_user_id, display_name, buyer_vk_id,
                    )
                return

            else:
                # Different client
                if is_receipt:
                    # Receipt from different client -> offer context switch with pending_is_receipt flag
                    try:
                        vk_user = db.get_or_create_vk_user(buyer_vk_id, display_name)
                        existing_reservation = db.get_active_reservation(vk_user.id)

                        current_buyer_name = current_context.get("buyer_display_name", "текущего клиента")
                        await message.answer(
                            f"Получен чек от {display_name}.\n"
                            f"Переключиться с {current_buyer_name} на {display_name}?",
                            keyboard=context_switch_keyboard()
                        )

                        # Build vk_message_ts for pending receipt context
                        vk_message_ts_iso = None
                        if forwarded.date:
                            from datetime import datetime as dt
                            vk_message_ts_iso = dt.utcfromtimestamp(forwarded.date).isoformat()

                        await storage.set(
                            message.from_id,
                            BotState.CONTEXT_SWITCH_CONFIRM,
                            pending_buyer_vk_id=vk_user.id,
                            pending_buyer_vk_api_id=buyer_vk_id,
                            pending_buyer_display_name=display_name,
                            pending_has_reservation=bool(existing_reservation),
                            pending_reservation_id=existing_reservation.id if existing_reservation else None,
                            pending_is_receipt=True,
                            pending_receipt_vk_message_ts=vk_message_ts_iso,
                            original_state=current_state,
                            original_context=current_context,
                        )
                    except db.DatabaseError as e:
                        logger.error(f"Database error checking reservation: {e}")
                        await message.answer("Ошибка при проверке брони. Попробуйте позже.")
                else:
                    # Plain text forward from different client in MAIN_MENU -> context switch (no receipt)
                    try:
                        vk_user = db.get_or_create_vk_user(buyer_vk_id, display_name)
                        existing_reservation = db.get_active_reservation(vk_user.id)

                        current_buyer_name = current_context.get("buyer_display_name", "текущего клиента")
                        await message.answer(
                            f"Вы работаете с {current_buyer_name}.\n"
                            f"Переключиться на {display_name}?",
                            keyboard=context_switch_keyboard()
                        )

                        await storage.set(
                            message.from_id,
                            BotState.CONTEXT_SWITCH_CONFIRM,
                            pending_buyer_vk_id=vk_user.id,
                            pending_buyer_vk_api_id=buyer_vk_id,
                            pending_buyer_display_name=display_name,
                            pending_has_reservation=bool(existing_reservation),
                            pending_reservation_id=existing_reservation.id if existing_reservation else None,
                            pending_is_receipt=False,
                            original_state=current_state,
                            original_context=current_context,
                        )
                    except db.DatabaseError as e:
                        logger.error(f"Database error checking reservation: {e}")
                        await message.answer("Ошибка при проверке брони. Попробуйте позже.")
                return

        # Same client in non-MAIN_MENU state - already working with them
        if buyer_vk_id == current_buyer_vk_api_id:
            await message.answer("Вы уже работаете с этим клиентом.")
            return

        # Different client in non-MAIN_MENU state - context switch confirmation
        current_buyer_name = current_context.get("buyer_display_name", "текущего клиента")

        await message.answer(
            f"Переключиться на {display_name}?\n"
            f"Текущая операция с {current_buyer_name} будет отменена.",
            keyboard=context_switch_keyboard()
        )

        # Get or create VK user to check for existing reservation
        try:
            vk_user = db.get_or_create_vk_user(buyer_vk_id, display_name)
            existing_reservation = db.get_active_reservation(vk_user.id)

            # Build vk_message_ts for pending receipt context (if receipt)
            vk_message_ts_iso = None
            if is_receipt and forwarded.date:
                from datetime import datetime as dt
                vk_message_ts_iso = dt.utcfromtimestamp(forwarded.date).isoformat()

            # Save pending switch info
            await storage.set(
                message.from_id,
                BotState.CONTEXT_SWITCH_CONFIRM,
                # Pending new client info
                pending_buyer_vk_id=vk_user.id,
                pending_buyer_vk_api_id=buyer_vk_id,
                pending_buyer_display_name=display_name,
                pending_has_reservation=bool(existing_reservation),
                pending_reservation_id=existing_reservation.id if existing_reservation else None,
                pending_is_receipt=is_receipt,
                pending_receipt_vk_message_ts=vk_message_ts_iso if is_receipt else None,
                # Original context to restore on "Нет"
                original_state=current_state,
                original_context=current_context,
            )

        except db.DatabaseError as e:
            logger.error(f"Database error checking reservation: {e}")
            await message.answer(
                "Ошибка при проверке брони. Попробуйте позже."
            )

        return

    # Seller is IDLE - proceed with create or show existing
    try:
        # Get or create VK user
        vk_user = db.get_or_create_vk_user(buyer_vk_id, display_name)

        # Check if user already has active reservation
        existing = db.get_active_reservation(vk_user.id)

        if existing:
            if is_receipt:
                # Receipt from IDLE -> enter payment flow directly
                await storage.set(
                    message.from_id,
                    BotState.MAIN_MENU,
                    reservation_id=existing.id,
                    buyer_vk_user_id=vk_user.id,
                    buyer_vk_api_id=buyer_vk_id,
                    buyer_display_name=display_name,
                    from_main_menu=True,
                )
                from bot.handlers.payment import start_payment_flow
                vk_message_ts = None
                if forwarded.date:
                    from datetime import datetime as dt
                    vk_message_ts = dt.utcfromtimestamp(forwarded.date)
                await start_payment_flow(
                    message, storage, existing.id, display_name,
                    vk_message_url=None,
                    vk_message_ts=vk_message_ts,
                )
                return

            # Scenario 2: Show main menu for existing reservation (non-receipt)
            await show_main_menu(
                message,
                storage,
                existing.id,
                vk_user.id,
                display_name,
                buyer_vk_id,
            )
            return

        # Scenario 1: Create new reservation (always, regardless of receipt for IDLE + no reservation)
        seller_id = db.get_default_seller_id()
        reservation = db.create_reservation(vk_user.id, seller_id)

        # Transition to AWAITING_ROW with context
        await message.ctx_api.messages.send(
            peer_id=message.peer_id,
            message=f"Создана новая бронь для {display_name} (ID: {reservation.id}).\n\n"
                    f"Введите номер ряда (1-24):",
            random_id=0,
        )

        await storage.set(
            message.from_id,
            BotState.AWAITING_ROW,
            reservation_id=reservation.id,
            buyer_vk_user_id=vk_user.id,
            buyer_vk_api_id=buyer_vk_id,
            buyer_display_name=display_name,
        )

    except db.DatabaseError as e:
        logger.error(f"Database error creating reservation: {e}")
        await message.answer(
            "Ошибка при создании брони. Попробуйте позже или обратитесь к администратору."
        )


async def awaiting_row_handler(message: Message, storage: RedisStorage):
    """
    Handle row input in AWAITING_ROW state.

    Validates row number and transitions to AWAITING_SEATS.

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

    # Update context with new row (replaces old current_row if exists)
    context['current_row'] = row

    # Transition to AWAITING_SEATS with updated context
    seat_count = get_seat_count(row)
    await message.answer(
        f"Ряд {row} (мест: {seat_count}).\n\n"
        f"Введите номера мест через пробел, запятую или диапазон.\n"
        f"Примеры: '5 6 7' или '5, 6, 7' или '5-7'"
    )

    await storage.set(message.from_id, BotState.AWAITING_SEATS, **context)


async def awaiting_seats_handler(message: Message, storage: RedisStorage):
    """
    Handle seat input in AWAITING_SEATS state.

    Parses seats, validates availability, and adds to reservation.

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

        # Transition to SEAT_ADDITION_MENU (preserve context)
        await storage.set(message.from_id, BotState.SEAT_ADDITION_MENU, **context)

    except db.SeatOccupiedError as e:
        # Show all conflicting seats at once
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
        error_lines.append("\nПопробуйте другие места:")
        await message.answer("\n".join(error_lines))
    except db.DatabaseError as e:
        logger.error(f"Error adding seats: {e}")
        await message.answer(
            "Ошибка при добавлении мест. Попробуйте позже или обратитесь к администратору."
        )


async def seat_addition_menu_handler(message: Message, storage: RedisStorage):
    """
    Handle buttons in SEAT_ADDITION_MENU state.

    Buttons:
    - "Добавить еще" - return to AWAITING_ROW
    - "Готово" - generate script (Phase 1) or return to main menu (Phase 2)

    Phase 1 flow (from_main_menu=False): generates script and clears state
    Phase 2 flow (from_main_menu=True): returns to main menu with updated seats

    Args:
        message: VK message
        storage: Redis storage instance
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)
    from_main_menu = context.get("from_main_menu", False)

    if text == "Добавить еще":
        # Return to AWAITING_ROW (preserve context including from_main_menu)
        await message.answer(
            "Введите номер ряда:",
            keyboard=get_empty_keyboard()
        )
        await storage.set(message.from_id, BotState.AWAITING_ROW, **context)

    elif text == "Готово":
        reservation_id = context.get("reservation_id")
        buyer_display_name = context.get("buyer_display_name")

        if not reservation_id:
            await message.answer("Ошибка: потерян контекст. Начните заново.")
            await storage.delete(message.from_id)
            return

        if from_main_menu:
            # Phase 2 behavior: return to main menu with updated seat list
            buyer_vk_user_id = context.get("buyer_vk_user_id")
            buyer_vk_api_id = context.get("buyer_vk_api_id")
            await show_main_menu(
                message,
                storage,
                reservation_id,
                buyer_vk_user_id,
                buyer_display_name,
                buyer_vk_api_id,
            )
        else:
            # Phase 1 behavior: generate script and clear state
            try:
                seats = db.get_reservation_seats(reservation_id)
                script = generate_reservation_script(
                    buyer_display_name=buyer_display_name,
                    seats=seats,
                )
                await message.answer(script, keyboard=get_empty_keyboard())
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
    # Get storage reference from bot
    storage = bot.state_dispenser

    # Wrap handlers with storage access
    async def forwarded_with_storage(message: Message):
        await forwarded_message_handler(message, storage)

    async def awaiting_row_with_storage(message: Message):
        await awaiting_row_handler(message, storage)

    async def awaiting_seats_with_storage(message: Message):
        await awaiting_seats_handler(message, storage)

    async def seat_menu_with_storage(message: Message):
        await seat_addition_menu_handler(message, storage)

    # Forwarded message (any state except active flows)
    bot.on.message(func=lambda msg: bool(msg.fwd_messages))(forwarded_with_storage)

    # State-specific handlers
    bot.on.message(state=BotState.AWAITING_ROW)(awaiting_row_with_storage)
    bot.on.message(state=BotState.AWAITING_SEATS)(awaiting_seats_with_storage)
    bot.on.message(state=BotState.SEAT_ADDITION_MENU)(seat_menu_with_storage)

    logger.info("Reservation handlers registered")
