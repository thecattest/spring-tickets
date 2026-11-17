"""Удаление мест из брони (ряд → места → подтверждение) и отмена брони целиком."""

import logging

from vkbottle.bot import Message

from tickets.bot import texts, vk
from tickets.bot.flows import common, menu, navigation
from tickets.bot.fsm.states import BotState
from tickets.bot.fsm.storage import RedisStorage
from tickets.bot.keyboards import confirmation_keyboard, get_empty_keyboard
from tickets.bot.messages import generate_reservation_script
from tickets.db import unit_of_work
from tickets.formatting import format_seat_ranges, pluralize_seats
from tickets.services import reservations, seats, users
from tickets.services.errors import NotAllowedError, ReservationNotActiveError, ServiceError

logger = logging.getLogger(__name__)


async def on_row(message: Message, storage: RedisStorage) -> None:
    """DELETING_ROW: ряд, в котором есть места этой брони."""
    try:
        row = common.parse_row(message.text)
    except common.InvalidInput as e:
        await vk.answer(message, str(e))
        return

    _, context = await storage.load(message.from_id)
    client = await common.require_client(message, storage, context, texts.ERR_CONTEXT_LOST_FWD)
    if client is None or not await common.require_active(message, storage, client):
        return
    async with unit_of_work() as session:
        in_row = await seats.of_reservation_in_row(session, client.reservation_id, row)
    if not in_row:
        await vk.answer(message, texts.ERR_ROW_NO_BOOKED_SEATS.format(row=row))
        return

    await vk.answer(
        message,
        texts.MSG_ENTER_SEATS_DELETE_WITH_BOOKED.format(
            row=row, seats=format_seat_ranges(sorted(in_row))
        ),
    )
    context.current_row = row
    await storage.save(message.from_id, BotState.DELETING_SEATS, context)


async def on_seats(message: Message, storage: RedisStorage) -> None:
    """DELETING_SEATS: места из брони, неоплаченные — к подтверждению."""
    _, context = await storage.load(message.from_id)
    client, row = context.client, context.current_row
    if client is None or row is None:
        await vk.answer(message, texts.ERR_CONTEXT_LOST_FWD)
        await storage.reset(message.from_id)
        return
    if not await common.require_active(message, storage, client):
        return

    try:
        parsed = await common.parse_seat_list(
            message.text, row, "membership", reservation_id=client.reservation_id
        )
    except common.InvalidInput as e:
        await vk.answer(message, str(e))
        return
    context.seats_to_delete = parsed
    await vk.answer(
        message,
        texts.MSG_CONFIRM_DELETE_SEATS.format(row=row, seats=", ".join(map(str, parsed))),
        keyboard=confirmation_keyboard(),
    )
    await storage.save(message.from_id, BotState.DELETION_CONFIRM, context)


async def on_delete_confirm(message: Message, storage: RedisStorage) -> None:
    """DELETION_CONFIRM: «Подтвердить» — освободить места и вернуться в меню брони."""
    _, context = await storage.load(message.from_id)
    client, row, to_delete = context.client, context.current_row, context.seats_to_delete
    if client is None or row is None or not to_delete:
        await vk.answer(message, texts.ERR_CONTEXT_LOST)
        await storage.reset(message.from_id)
        return

    confirmed = common.parse_confirmation(message.text)
    if confirmed is None:
        await vk.answer(message, texts.PROMPT_SELECT_ACTION, keyboard=confirmation_keyboard())
        return
    if not confirmed:
        await navigation.on_cancel(message, storage)  # как кнопка «Отмена»
        return

    try:
        async with unit_of_work() as session:
            seller = await users.require_app_user(session, message.from_id)
            released = await reservations.remove_seats(
                session, client.reservation_id, row, to_delete, seller.id
            )
            remaining = await seats.of_reservation(session, client.reservation_id)
    except ReservationNotActiveError:
        await common.require_active(message, storage, client)
        return
    except ServiceError as e:
        logger.error("Error releasing seats: %s", e)
        await vk.answer(
            message, texts.ERR_DELETE_SEATS.format(error=e), keyboard=get_empty_keyboard()
        )
        await menu.show(message, storage, client)
        return

    await vk.answer(
        message,
        texts.MSG_SEATS_DELETED.format(count=released, count_word=pluralize_seats(released)),
        keyboard=get_empty_keyboard(),
    )
    if remaining:
        script = generate_reservation_script(buyer_display_name=client.buyer_name, seats=remaining)
        await vk.answer(message, script, keyboard=get_empty_keyboard())
    await menu.show(message, storage, client)


async def on_cancel_confirm(message: Message, storage: RedisStorage) -> None:
    """CANCEL_CONFIRM: «Подтвердить» — отменить бронь (с оплаченными местами — только админ)."""
    _, context = await storage.load(message.from_id)
    client = await common.require_client(message, storage, context, texts.ERR_CONTEXT_LOST)
    if client is None:
        return

    confirmed = common.parse_confirmation(message.text)
    if confirmed is None:
        await vk.answer(message, texts.PROMPT_SELECT_ACTION, keyboard=confirmation_keyboard())
        return
    if not confirmed:
        await navigation.on_cancel(message, storage)  # как кнопка «Отмена»
        return

    try:
        async with unit_of_work() as session:
            seller = await users.require_app_user(session, message.from_id)
            await reservations.cancel(
                session,
                client.reservation_id,
                seller.id,
                is_admin=await users.is_admin(session, message.from_id),
            )
    except NotAllowedError:
        await vk.answer(message, texts.ERR_PAID_CANCEL_ADMIN_ONLY, keyboard=get_empty_keyboard())
        await menu.show(message, storage, client)
        return
    except ReservationNotActiveError:
        await common.require_active(message, storage, client)
        return
    except ServiceError as e:
        logger.error("Error cancelling reservation: %s", e)
        await vk.answer(
            message, texts.ERR_CANCEL_BOOKING.format(error=e), keyboard=get_empty_keyboard()
        )
        await menu.show(message, storage, client)
        return

    await vk.answer(message, texts.MSG_BOOKING_CANCELLED, keyboard=get_empty_keyboard())
    await storage.reset(message.from_id)
