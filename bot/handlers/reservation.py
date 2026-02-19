"""
Reservation creation and management handlers.

Handles:
- Forwarded message (create reservation)
- Row input (AWAITING_ROW state)
- Seat input (AWAITING_SEATS state)
- Seat addition menu (SEAT_ADDITION_MENU state)
"""

import logging
from vkbottle.bot import Message
from vkbottle import VKAPIError

from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage
from bot.utils import db
from bot.utils.layout import get_seat_count
from bot.keyboards import seat_addition_menu_keyboard, get_empty_keyboard, context_switch_keyboard, main_menu_keyboard
from bot.messages import generate_reservation_script
from models.base import SeatStatus
from bot.handlers.menu import show_main_menu
from bot.constants import Btn
from bot import texts

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
                            texts.MSG_SWITCH_RECEIPT.format(name=display_name, current=current_buyer_name),
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
                        await message.answer(texts.ERR_DB_CHECK_BOOKING)
                else:
                    # Plain text forward from different client in MAIN_MENU -> context switch (no receipt)
                    try:
                        vk_user = db.get_or_create_vk_user(buyer_vk_id, display_name)
                        existing_reservation = db.get_active_reservation(vk_user.id)

                        current_buyer_name = current_context.get("buyer_display_name", "текущего клиента")
                        await message.answer(
                            texts.MSG_SWITCH_PLAIN.format(current=current_buyer_name, name=display_name),
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
                        await message.answer(texts.ERR_DB_CHECK_BOOKING)
                return

        # Same client in non-MAIN_MENU state - already working with them
        if buyer_vk_id == current_buyer_vk_api_id:
            await message.answer(texts.ERR_ALREADY_WORKING)
            return

        # Different client in non-MAIN_MENU state - context switch confirmation
        current_buyer_name = current_context.get("buyer_display_name", "текущего клиента")

        await message.answer(
            texts.MSG_SWITCH_TO_CLIENT.format(name=display_name, current=current_buyer_name),
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
            await message.answer(texts.ERR_DB_CHECK_BOOKING)

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
        seller_id = db.get_seller_id(message.from_id)
        reservation = db.create_reservation(vk_user.id, seller_id)

        # Transition to AWAITING_ROW with context
        await message.ctx_api.messages.send(
            peer_id=message.peer_id,
            message=texts.MSG_NEW_BOOKING_CREATED.format(name=display_name, id=reservation.id),
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
        await message.answer(texts.ERR_DB_CREATE_BOOKING)


async def awaiting_row_handler(message: Message, storage: RedisStorage):
    """
    Handle row input in AWAITING_ROW state.

    Validates row number and transitions to AWAITING_SEATS.

    Args:
        message: VK message
        storage: Redis storage instance
    """
    from bot.steps import handle_row_input

    result = handle_row_input(message.text)
    if not result.ok:
        await message.answer(result.error_text)
        return
    row = result.row

    # Get existing context to preserve it
    context = await storage.get_context(message.from_id)

    # Update context with new row (replaces old current_row if exists)
    context['current_row'] = row

    # Transition to AWAITING_SEATS with updated context
    seat_count = get_seat_count(row)
    await message.answer(
        texts.MSG_ROW_SEAT_COUNT.format(row=row, seat_count=seat_count)
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
    from bot.steps import handle_seat_input

    context = await storage.get_context(message.from_id)

    row = context.get("current_row")
    reservation_id = context.get("reservation_id")

    if not row or not reservation_id:
        await message.answer(texts.ERR_CONTEXT_LOST_FWD)
        await storage.delete(message.from_id)
        return

    result = handle_seat_input(message.text, row=row, mode="availability")
    if not result.ok:
        await message.answer(result.error_text)
        return
    seats = result.seats

    # All seats available - add them
    try:
        seller_id = db.get_seller_id(message.from_id)
        assignments = db.add_seats_to_reservation(reservation_id, row, seats, seller_id)

        # Get total seat count for reservation
        all_seats = db.get_reservation_seats(reservation_id)
        total_count = len(all_seats)

        # Success message
        await message.answer(
            texts.MSG_SEATS_ADDED.format(
                count=len(seats),
                row=row,
                seats=", ".join(map(str, seats)),
                total=total_count,
            ),
            keyboard=seat_addition_menu_keyboard()
        )

        # Transition to SEAT_ADDITION_MENU (preserve context)
        await storage.set(message.from_id, BotState.SEAT_ADDITION_MENU, **context)

    except db.SeatOccupiedError as e:
        # Show all conflicting seats at once (race condition guard — steps.py already checked availability)
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
        await message.answer(texts.ERR_DB_ADD_SEATS)


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

    if text == Btn.ADD_MORE:
        # Return to AWAITING_ROW (preserve context including from_main_menu)
        await message.answer(
            texts.PROMPT_ENTER_ROW,
            keyboard=get_empty_keyboard()
        )
        await storage.set(message.from_id, BotState.AWAITING_ROW, **context)

    elif text == Btn.DONE:
        reservation_id = context.get("reservation_id")
        buyer_display_name = context.get("buyer_display_name")

        if not reservation_id:
            await message.answer(texts.ERR_CONTEXT_LOST)
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
                await message.answer(texts.ERR_DB_GENERATE_SCRIPT)

    else:
        # Unknown button
        await message.answer(
            texts.PROMPT_SELECT_ACTION,
            keyboard=seat_addition_menu_keyboard()
        )
