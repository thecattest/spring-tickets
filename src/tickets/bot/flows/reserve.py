"""
Резервы (только админ): места под гостей без брони, с обязательным комментарием.

«Резерв» → Добавить: ряд → места → комментарий; Удалить: ряд → места → подтверждение.
"""

import logging

from vkbottle.bot import Message

from tickets.bot import auth, texts, vk
from tickets.bot.constants import Btn
from tickets.bot.flows import common
from tickets.bot.fsm.context import Context
from tickets.bot.fsm.states import BotState
from tickets.bot.fsm.storage import RedisStorage
from tickets.bot.keyboards import confirmation_keyboard, get_empty_keyboard, reserve_action_keyboard
from tickets.bot.messages import format_reserves_list
from tickets.db import unit_of_work
from tickets.formatting import format_seat_ranges, pluralize_seats
from tickets.hall import get_seat_count
from tickets.services import seats
from tickets.services.errors import SeatOccupiedError, ServiceError

logger = logging.getLogger(__name__)


async def show_actions(message: Message, storage: RedisStorage, admin_user_id: int) -> None:
    """Список резервов и кнопки Добавить / Удалить."""
    async with unit_of_work() as session:
        reserves = await seats.active_reserves(session)
    await vk.answer(
        message,
        texts.MSG_RESERVE_ACTION_HEADER.format(reserves=format_reserves_list(reserves)),
        keyboard=reserve_action_keyboard(),
    )
    await storage.save(
        message.from_id, BotState.RESERVE_ACTION, Context(admin_user_id=admin_user_id)
    )


@auth.requires_admin(denied=texts.ERR_RESERVE_ADMIN_ONLY)
async def on_command(message: Message, storage: RedisStorage) -> None:
    """«Резерв»."""
    user = await auth.current_user(message)
    if user is None:  # сняли роль между проверкой и этой строкой
        await vk.answer(message, texts.ERR_RESERVE_ADMIN_ONLY)
        return
    await show_actions(message, storage, user.id)


async def _back_to_actions(
    message: Message, storage: RedisStorage, text: str, admin_user_id: int
) -> None:
    await vk.answer(message, text, keyboard=reserve_action_keyboard())
    await storage.save(
        message.from_id, BotState.RESERVE_ACTION, Context(admin_user_id=admin_user_id)
    )


_ACTIONS: dict[str, BotState] = {
    Btn.ADD: BotState.RESERVE_ADDING_ROW,
    Btn.DELETE: BotState.RESERVE_REMOVING_ROW,
}


async def on_action(message: Message, storage: RedisStorage) -> None:
    """RESERVE_ACTION: Добавить / Удалить."""
    _, context = await storage.load(message.from_id)
    next_state = _ACTIONS.get(message.text.strip())
    if next_state is None:
        await vk.answer(message, texts.PROMPT_SELECT_ACTION, keyboard=reserve_action_keyboard())
        return
    await vk.answer(message, texts.PROMPT_ENTER_ROW, keyboard=get_empty_keyboard())
    await storage.save(message.from_id, next_state, context)


# --- добавить резерв --------------------------------------------------------


async def on_adding_row(message: Message, storage: RedisStorage) -> None:
    try:
        row = common.parse_row(message.text)
    except common.InvalidInput as e:
        await vk.answer(message, str(e))
        return
    async with unit_of_work() as session:
        available = await seats.available_in_row(session, row)
    if not available:
        await vk.answer(message, texts.ERR_ROW_NO_AVAILABLE_SEATS.format(row=row))
        return

    seat_count = get_seat_count(row)
    occupied = sorted(set(range(1, seat_count + 1)) - set(available))
    word = pluralize_seats(seat_count)
    if occupied:
        prompt = texts.MSG_ENTER_SEATS_RESERVE_WITH_OCCUPIED.format(
            row=row,
            seat_count=seat_count,
            seat_count_word=word,
            occupied=format_seat_ranges(occupied),
        )
    else:
        prompt = texts.MSG_ENTER_SEATS_RESERVE.format(
            row=row, seat_count=seat_count, seat_count_word=word
        )
    await vk.answer(message, prompt)

    _, context = await storage.load(message.from_id)
    context.current_row = row
    await storage.save(message.from_id, BotState.RESERVE_ADDING_SEATS, context)


async def on_adding_seats(message: Message, storage: RedisStorage) -> None:
    _, context = await storage.load(message.from_id)
    if context.current_row is None:
        await vk.answer(message, texts.ERR_CONTEXT_LOST_RESERVE)
        await storage.reset(message.from_id)
        return
    try:
        parsed = await common.parse_seat_list(message.text, context.current_row, "availability")
    except common.InvalidInput as e:
        await vk.answer(message, str(e))
        return
    context.reserve_seats = parsed
    await vk.answer(message, texts.PROMPT_ENTER_COMMENT)
    await storage.save(message.from_id, BotState.RESERVE_COMMENT, context)


async def on_comment(message: Message, storage: RedisStorage) -> None:
    comment = message.text.strip()
    if not comment:
        await vk.answer(message, texts.PROMPT_COMMENT_REQUIRED)
        return
    _, context = await storage.load(message.from_id)
    row, seat_list, admin_id = context.current_row, context.reserve_seats, context.admin_user_id
    if row is None or not seat_list or admin_id is None:
        await vk.answer(message, texts.ERR_CONTEXT_LOST_RESERVE)
        await storage.reset(message.from_id)
        return

    try:
        async with unit_of_work() as session:
            await seats.add_reserve(session, row, seat_list, comment, admin_id)
    except SeatOccupiedError as e:
        await vk.answer(
            message, await common.seat_conflicts_text(e.conflicts, "Введите другие места:")
        )
        context.reserve_seats = []
        await storage.save(message.from_id, BotState.RESERVE_ADDING_SEATS, context)
        return
    except ServiceError as e:
        logger.error("Error adding reserve: %s", e)
        await _back_to_actions(message, storage, texts.ERR_RESERVE_CREATE.format(error=e), admin_id)
        return

    created = texts.MSG_RESERVE_CREATED.format(
        row=row, seats=format_seat_ranges(sorted(seat_list)), comment=comment
    )
    await _back_to_actions(message, storage, created, admin_id)


# --- снять резерв -----------------------------------------------------------


async def on_removing_row(message: Message, storage: RedisStorage) -> None:
    try:
        row = common.parse_row(message.text)
    except common.InvalidInput as e:
        await vk.answer(message, str(e))
        return
    async with unit_of_work() as session:
        reserved = await seats.reserved_in_row(session, row)
    if not reserved:
        await vk.answer(message, texts.ERR_ROW_NO_RESERVED_SEATS.format(row=row))
        return
    await vk.answer(
        message,
        texts.MSG_ENTER_SEATS_UNRESERVE_WITH_RESERVED.format(
            row=row, reserved=format_seat_ranges(sorted(reserved))
        ),
    )
    _, context = await storage.load(message.from_id)
    context.current_row = row
    await storage.save(message.from_id, BotState.RESERVE_REMOVING_SEATS, context)


async def on_removing_seats(message: Message, storage: RedisStorage) -> None:
    _, context = await storage.load(message.from_id)
    row = context.current_row
    if row is None:
        await vk.answer(message, texts.ERR_CONTEXT_LOST_RESERVE)
        await storage.reset(message.from_id)
        return
    try:
        parsed = await common.parse_seat_list(message.text, row, "layout_only")
    except common.InvalidInput as e:
        await vk.answer(message, str(e))
        return
    seat_list = parsed

    async with unit_of_work() as session:
        notes = await seats.reserve_notes(session, row, seat_list)
    unique = sorted({n for n in notes.values() if n})
    note_text = "\nКомментарий: " + ", ".join(unique) if unique else ""
    await vk.answer(
        message,
        texts.MSG_CONFIRM_UNRESERVE.format(row=row, seats=format_seat_ranges(sorted(seat_list)))
        + note_text,
        keyboard=confirmation_keyboard(),
    )
    context.reserve_seats_to_remove = seat_list
    await storage.save(message.from_id, BotState.RESERVE_REMOVE_CONFIRM, context)


async def on_remove_confirm(message: Message, storage: RedisStorage) -> None:
    _, context = await storage.load(message.from_id)
    row, seat_list, admin_id = (
        context.current_row,
        context.reserve_seats_to_remove,
        context.admin_user_id,
    )
    if row is None or not seat_list or admin_id is None:
        await vk.answer(message, texts.ERR_CONTEXT_LOST_RESERVE)
        await storage.reset(message.from_id)
        return

    confirmed = common.parse_confirmation(message.text)
    if confirmed is None:
        await vk.answer(message, texts.PROMPT_SELECT_ACTION, keyboard=confirmation_keyboard())
        return
    if confirmed is False:
        await _back_to_actions(message, storage, texts.MSG_CANCELLED_BRIEF, admin_id)
        return

    try:
        async with unit_of_work() as session:
            previous = await seats.release_reserve(session, row, seat_list, admin_id)
    except ServiceError as e:
        logger.error("Error releasing reserve: %s", e)
        await _back_to_actions(message, storage, texts.ERR_RESERVE_REMOVE.format(error=e), admin_id)
        return

    result = f"Резерв снят:\nРяд {row}, места: {format_seat_ranges(sorted(seat_list))}"
    with_notes = [n for n in previous if n.get("note")]
    if with_notes:
        result += "\n\nПредыдущие комментарии:" + "".join(
            f"\n• Место {n['seat']}: {n['note']}" for n in with_notes
        )
    await _back_to_actions(message, storage, result, admin_id)
