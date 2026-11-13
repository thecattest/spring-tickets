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

from vkbottle.bot import Message

from bot import texts
from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage
from bot.handlers.menu import show_main_menu
from bot.keyboards import confirmation_keyboard, get_empty_keyboard
from bot.utils import db

logger = logging.getLogger(__name__)


async def deleting_row_handler(message: Message, storage: RedisStorage):
    """
    Handle row number input during deletion.

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

    # Get existing context (need reservation_id for early validation)
    context = await storage.get_context(message.from_id)
    reservation_id = context.get("reservation_id")
    if not reservation_id:
        await message.answer(texts.ERR_CONTEXT_LOST_FWD)
        await storage.delete(message.from_id)
        return

    # Early row validation: check if reservation has seats in this row
    booked = db.get_reservation_booked_seats_in_row(reservation_id, row)
    if not booked:
        await message.answer(texts.ERR_ROW_NO_BOOKED_SEATS.format(row=row))
        return

    # Update context with current_row
    context["current_row"] = row

    # Transition to DELETING_SEATS — show which seats from this reservation are in the row
    from bot.utils.formatting import format_seat_ranges

    booked_str = format_seat_ranges(sorted(booked))
    await message.answer(texts.MSG_ENTER_SEATS_DELETE_WITH_BOOKED.format(row=row, seats=booked_str))

    await storage.set(message.from_id, BotState.DELETING_SEATS, **context)


async def deleting_seats_handler(message: Message, storage: RedisStorage):
    """
    Handle seat numbers input during deletion.

    Args:
        message: VK message
        storage: Redis storage instance
    """
    context = await storage.get_context(message.from_id)

    row = context.get("current_row")
    reservation_id = context.get("reservation_id")

    if not row or not reservation_id:
        await message.answer(texts.ERR_CONTEXT_LOST_FWD)
        await storage.delete(message.from_id)
        return

    from bot.steps import handle_seat_input

    result = handle_seat_input(
        message.text, row=row, mode="membership", reservation_id=reservation_id
    )
    if not result.ok:
        await message.answer(result.error_text)
        return
    seats = result.seats

    # All seats are BOOKED and belong to reservation - proceed to confirmation
    context["seats_to_delete"] = seats

    await message.answer(
        texts.MSG_CONFIRM_DELETE_SEATS.format(row=row, seats=", ".join(map(str, seats))),
        keyboard=confirmation_keyboard(),
    )

    await storage.set(message.from_id, BotState.DELETION_CONFIRM, **context)


async def deletion_confirm_handler(message: Message, storage: RedisStorage):
    """
    Handle deletion confirmation.

    Args:
        message: VK message
        storage: Redis storage instance
    """
    from bot.steps import handle_confirmation

    context = await storage.get_context(message.from_id)

    reservation_id = context.get("reservation_id")
    buyer_vk_user_id = context.get("buyer_vk_user_id")
    buyer_vk_api_id = context.get("buyer_vk_api_id")
    buyer_display_name = context.get("buyer_display_name")
    row = context.get("current_row")
    seats = context.get("seats_to_delete")

    if not all([reservation_id, row, seats]):
        await message.answer(texts.ERR_CONTEXT_LOST)
        await storage.delete(message.from_id)
        return

    confirmed = handle_confirmation(message.text)
    if confirmed is True:
        # Release seats
        try:
            seller_id = db.get_seller_id(message.from_id)
            released_count = db.release_seats(reservation_id, row, seats, seller_id)

            from bot.utils.formatting import pluralize_seats

            await message.answer(
                texts.MSG_SEATS_DELETED.format(
                    count=released_count, count_word=pluralize_seats(released_count)
                ),
                keyboard=get_empty_keyboard(),
            )

            # Send updated client script if seats remain
            remaining = db.get_reservation_seats(reservation_id)
            if remaining:
                from bot.messages import generate_reservation_script

                script = generate_reservation_script(
                    buyer_display_name=buyer_display_name,
                    seats=remaining,
                )
                await message.answer(script, keyboard=get_empty_keyboard())

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
                texts.ERR_DELETE_SEATS.format(error=e), keyboard=get_empty_keyboard()
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

    elif confirmed is False:
        await message.answer(texts.MSG_CANCELLED_BRIEF, keyboard=get_empty_keyboard())

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
        await message.answer(texts.PROMPT_SELECT_ACTION, keyboard=confirmation_keyboard())


async def cancel_confirm_handler(message: Message, storage: RedisStorage):
    """
    Handle reservation cancellation confirmation.

    Args:
        message: VK message
        storage: Redis storage instance
    """
    from bot.steps import handle_confirmation

    context = await storage.get_context(message.from_id)

    reservation_id = context.get("reservation_id")
    buyer_vk_user_id = context.get("buyer_vk_user_id")
    buyer_vk_api_id = context.get("buyer_vk_api_id")
    buyer_display_name = context.get("buyer_display_name")

    if not reservation_id:
        await message.answer(texts.ERR_CONTEXT_LOST)
        await storage.delete(message.from_id)
        return

    confirmed = handle_confirmation(message.text)
    if confirmed is True:
        # Check if user is admin
        is_admin = db.is_user_admin(message.from_id)

        try:
            seller_id = db.get_seller_id(message.from_id)
            db.cancel_reservation(reservation_id, seller_id, is_admin)

            await message.answer(texts.MSG_BOOKING_CANCELLED, keyboard=get_empty_keyboard())

            # Clear FSM state (return to IDLE)
            await storage.delete(message.from_id)

        except db.PermissionError:
            await message.answer(texts.ERR_PAID_CANCEL_ADMIN_ONLY, keyboard=get_empty_keyboard())

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
                texts.ERR_CANCEL_BOOKING.format(error=e), keyboard=get_empty_keyboard()
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

    elif confirmed is False:
        await message.answer(texts.MSG_CANCELLED_BRIEF, keyboard=get_empty_keyboard())

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
        await message.answer(texts.PROMPT_SELECT_ACTION, keyboard=confirmation_keyboard())
