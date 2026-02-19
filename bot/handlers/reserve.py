"""
Reserve management handlers (admin only).

Handles:
- /Резерв command (entry point, admin check)
- Add reserve flow (RESERVE_ACTION -> RESERVE_ADDING_ROW -> RESERVE_ADDING_SEATS -> RESERVE_COMMENT -> RESERVE_ACTION)
- Remove reserve flow (RESERVE_ACTION -> RESERVE_REMOVING_ROW -> RESERVE_REMOVING_SEATS -> RESERVE_REMOVE_CONFIRM -> RESERVE_ACTION)

Reserves are SeatAssignment rows with status=RESERVED, reservation_id=None, and a mandatory comment (note).
"""

import logging
from vkbottle.bot import Message

from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage
from bot.utils import db
from bot.utils.layout import get_seat_count
from bot.keyboards import (
    reserve_action_keyboard,
    confirmation_keyboard,
    get_empty_keyboard,
)
from bot.messages import format_reserves_list
from bot.utils.formatting import format_seat_ranges
from bot.constants import Btn
from bot import texts
from models.base import SeatStatus

logger = logging.getLogger(__name__)


async def reserve_command_handler(message: Message, storage: RedisStorage):
    """
    /Резерв command handler.

    Checks admin status and shows reserve action keyboard or rejection.
    """
    is_admin = db.is_user_admin(message.from_id)

    if not is_admin:
        await message.answer(texts.ERR_RESERVE_ADMIN_ONLY)
        return

    # Resolve admin's AppUser.id for DB writes
    app_user = db.get_app_user_by_vk_id(message.from_id)
    if not app_user:
        await message.answer(texts.ERR_ACCOUNT_NOT_FOUND)
        return

    reserves = db.get_active_reserves()
    reserves_text = format_reserves_list(reserves)

    await message.answer(
        texts.MSG_RESERVE_ACTION_HEADER.format(reserves=reserves_text),
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

    if text == Btn.ADD:
        await message.answer(
            texts.PROMPT_ENTER_ROW,
            keyboard=get_empty_keyboard()
        )
        await storage.set(message.from_id, BotState.RESERVE_ADDING_ROW, **context)

    elif text == Btn.DELETE:
        await message.answer(
            texts.PROMPT_ENTER_ROW,
            keyboard=get_empty_keyboard()
        )
        await storage.set(message.from_id, BotState.RESERVE_REMOVING_ROW, **context)

    else:
        await message.answer(
            texts.PROMPT_SELECT_ACTION,
            keyboard=reserve_action_keyboard()
        )


async def reserve_adding_row_handler(message: Message, storage: RedisStorage):
    """
    Handle row number input during add reserve (RESERVE_ADDING_ROW state).
    """
    from bot.steps import handle_row_input

    result = handle_row_input(message.text)
    if not result.ok:
        await message.answer(result.error_text)
        return
    row = result.row

    # Get existing context to preserve admin_user_id
    context = await storage.get_context(message.from_id)
    context['current_row'] = row

    seat_count = get_seat_count(row)
    await message.answer(
        texts.MSG_ENTER_SEATS_RESERVE.format(row=row, seat_count=seat_count)
    )
    await storage.set(message.from_id, BotState.RESERVE_ADDING_SEATS, **context)


async def reserve_adding_seats_handler(message: Message, storage: RedisStorage):
    """
    Handle seat numbers input during add reserve (RESERVE_ADDING_SEATS state).
    """
    from bot.steps import handle_seat_input

    context = await storage.get_context(message.from_id)

    row = context.get("current_row")
    if not row:
        await message.answer(texts.ERR_CONTEXT_LOST_RESERVE)
        await storage.delete(message.from_id)
        return

    result = handle_seat_input(message.text, row=row, mode="layout_only")
    if not result.ok:
        await message.answer(result.error_text)
        return
    seats = result.seats

    # Store seats and prompt for comment
    context['reserve_seats'] = seats
    await message.answer(texts.PROMPT_ENTER_COMMENT)
    await storage.set(message.from_id, BotState.RESERVE_COMMENT, **context)


async def reserve_comment_handler(message: Message, storage: RedisStorage):
    """
    Handle comment input during add reserve (RESERVE_COMMENT state).
    """
    comment = message.text.strip()

    if not comment:
        await message.answer(texts.PROMPT_COMMENT_REQUIRED)
        return

    context = await storage.get_context(message.from_id)
    row = context.get("current_row")
    seats = context.get("reserve_seats")
    admin_user_id = context.get("admin_user_id")

    if not all([row, seats, admin_user_id]):
        await message.answer(texts.ERR_CONTEXT_LOST_RESERVE)
        await storage.delete(message.from_id)
        return

    try:
        db.add_reserve(row, seats, comment, admin_user_id)

        seats_str = format_seat_ranges(sorted(seats))
        await message.answer(
            texts.MSG_RESERVE_CREATED.format(row=row, seats=seats_str, comment=comment),
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
            texts.ERR_RESERVE_CREATE.format(error=e),
            keyboard=reserve_action_keyboard()
        )
        await storage.set(message.from_id, BotState.RESERVE_ACTION, admin_user_id=admin_user_id)


async def reserve_removing_row_handler(message: Message, storage: RedisStorage):
    """
    Handle row number input during remove reserve (RESERVE_REMOVING_ROW state).
    """
    from bot.steps import handle_row_input

    result = handle_row_input(message.text)
    if not result.ok:
        await message.answer(result.error_text)
        return
    row = result.row

    # Get existing context to preserve admin_user_id
    context = await storage.get_context(message.from_id)
    context['current_row'] = row

    seat_count = get_seat_count(row)
    await message.answer(
        texts.MSG_ENTER_SEATS_UNRESERVE.format(row=row, seat_count=seat_count)
    )
    await storage.set(message.from_id, BotState.RESERVE_REMOVING_SEATS, **context)


async def reserve_removing_seats_handler(message: Message, storage: RedisStorage):
    """
    Handle seat numbers input during remove reserve (RESERVE_REMOVING_SEATS state).
    """
    from bot.steps import handle_seat_input

    context = await storage.get_context(message.from_id)

    row = context.get("current_row")
    if not row:
        await message.answer(texts.ERR_CONTEXT_LOST_RESERVE)
        await storage.delete(message.from_id)
        return

    result = handle_seat_input(message.text, row=row, mode="layout_only")
    if not result.ok:
        await message.answer(result.error_text)
        return
    seats = result.seats

    # Store seats and show confirmation
    context['reserve_seats_to_remove'] = seats
    seats_str = format_seat_ranges(sorted(seats))

    await message.answer(
        texts.MSG_CONFIRM_UNRESERVE.format(row=row, seats=seats_str),
        keyboard=confirmation_keyboard()
    )
    await storage.set(message.from_id, BotState.RESERVE_REMOVE_CONFIRM, **context)


async def reserve_remove_confirm_handler(message: Message, storage: RedisStorage):
    """
    Handle remove reserve confirmation (RESERVE_REMOVE_CONFIRM state).
    """
    from bot.steps import handle_confirmation

    context = await storage.get_context(message.from_id)

    row = context.get("current_row")
    seats = context.get("reserve_seats_to_remove")
    admin_user_id = context.get("admin_user_id")

    if not all([row, seats, admin_user_id]):
        await message.answer(texts.ERR_CONTEXT_LOST_RESERVE)
        await storage.delete(message.from_id)
        return

    confirmed = handle_confirmation(message.text)
    if confirmed is True:
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
                texts.ERR_RESERVE_REMOVE.format(error=e),
                keyboard=reserve_action_keyboard()
            )
            await storage.set(message.from_id, BotState.RESERVE_ACTION, admin_user_id=admin_user_id)

    elif confirmed is False:
        await message.answer(
            texts.MSG_CANCELLED_BRIEF,
            keyboard=reserve_action_keyboard()
        )
        await storage.set(message.from_id, BotState.RESERVE_ACTION, admin_user_id=admin_user_id)

    else:
        # Unknown input - re-show keyboard
        await message.answer(
            texts.PROMPT_SELECT_ACTION,
            keyboard=confirmation_keyboard()
        )
