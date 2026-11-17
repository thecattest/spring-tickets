"""Меню брони (Добавить / Удалить / Удалить все / Оплата) и переключение на другого клиента."""

import logging

from vkbottle.bot import Message

from tickets.bot import texts, vk
from tickets.bot.constants import Btn
from tickets.bot.flows import common, payment
from tickets.bot.fsm.context import Client, Context
from tickets.bot.fsm.states import BotState
from tickets.bot.fsm.storage import RedisStorage
from tickets.bot.keyboards import (
    confirmation_keyboard,
    context_switch_keyboard,
    get_empty_keyboard,
    main_menu_keyboard,
)
from tickets.bot.messages import format_reservation_seats
from tickets.db import unit_of_work
from tickets.formatting import pluralize_seats
from tickets.models.base import SeatStatus
from tickets.services import reservations, seats, users
from tickets.services.errors import ServiceError

logger = logging.getLogger(__name__)


async def show(message: Message, storage: RedisStorage, client: Client) -> None:
    """Меню брони клиента: места по статусам и кнопки действий."""
    try:
        async with unit_of_work() as session:
            seat_list = await seats.of_reservation(session, client.reservation_id)
    except ServiceError as e:
        logger.error("Error displaying main menu: %s", e)
        await vk.answer(message, texts.ERR_DB_LOAD_BOOKING)
        return
    text = (
        f"Бронь #{client.reservation_id} — {client.buyer_name}\n\n"
        f"{format_reservation_seats(seat_list)}\n\nВыберите действие:"
    )
    await vk.answer(message, text, keyboard=main_menu_keyboard())
    await storage.save(
        message.from_id, BotState.MAIN_MENU, Context(client=client, from_main_menu=True)
    )


async def on_menu_button(message: Message, storage: RedisStorage) -> None:
    """MAIN_MENU: кнопки меню брони."""
    _, context = await storage.load(message.from_id)
    client = await common.require_client(message, storage, context, texts.ERR_CONTEXT_LOST)
    if client is None or not await common.require_active(message, storage, client):
        return
    text = message.text.strip()

    if text == Btn.ADD:
        await vk.answer(message, texts.PROMPT_ENTER_ROW, keyboard=get_empty_keyboard())
        await storage.save(message.from_id, BotState.AWAITING_ROW, context)
        return

    if text == Btn.PAYMENT:
        # Оплата начинается с пересылки чека, не с кнопки
        await vk.answer(message, texts.MSG_PAYMENT_SEND_RECEIPT, keyboard=main_menu_keyboard())
        return

    if text not in (Btn.DELETE, Btn.DELETE_ALL):
        await vk.answer(message, texts.PROMPT_SELECT_ACTION, keyboard=main_menu_keyboard())
        return

    try:
        async with unit_of_work() as session:
            seat_list = await seats.of_reservation(session, client.reservation_id)
            is_admin = await users.is_admin(session, message.from_id)
    except ServiceError as e:
        logger.error("Error checking seats: %s", e)
        await vk.answer(message, texts.ERR_DB_CHECK_SEATS, keyboard=main_menu_keyboard())
        return

    if text == Btn.DELETE:
        if not seat_list:
            await vk.answer(message, texts.ERR_NO_SEATS_TO_DELETE, keyboard=main_menu_keyboard())
            return
        await vk.answer(message, texts.PROMPT_ENTER_ROW_DELETE, keyboard=get_empty_keyboard())
        await storage.save(message.from_id, BotState.DELETING_ROW, context)
        return

    # Удалить все — отмена брони
    if not seat_list:
        await vk.answer(message, texts.ERR_NO_SEATS, keyboard=main_menu_keyboard())
        return
    paid = sum(1 for s in seat_list if s.status == SeatStatus.PAID)
    booked = sum(1 for s in seat_list if s.status == SeatStatus.BOOKED)
    total = f"Всего: {len(seat_list)} {pluralize_seats(len(seat_list))}"
    if paid and not is_admin:
        await vk.answer(message, texts.ERR_PAID_CANCEL_ADMIN_ONLY, keyboard=main_menu_keyboard())
        return
    if paid:
        prompt = (
            f"Отменить бронь {client.buyer_name}?\n\n{total} (бронь: {booked}, оплачено: {paid})"
            f"\n\nВ брони {paid} оплаченных {pluralize_seats(paid)}."
        )
    else:
        prompt = f"Отменить бронь {client.buyer_name}?\n\n{total}"
    await vk.answer(message, prompt, keyboard=confirmation_keyboard())
    await storage.save(message.from_id, BotState.CANCEL_CONFIRM, context)


async def on_switch_answer(message: Message, storage: RedisStorage) -> None:
    """CONTEXT_SWITCH_CONFIRM: «Да» — к новому клиенту, «Нет» — вернуться к прежнему."""
    _, context = await storage.load(message.from_id)
    confirmed = common.parse_confirmation(message.text)

    if confirmed is False:
        saved = context.saved
        if saved and saved.state != BotState.IDLE:
            await storage.save(message.from_id, saved.state, saved.context)
            name = (
                saved.context.client.buyer_name if saved.context.client else "предыдущим клиентом"
            )
            await vk.answer(message, texts.MSG_CONTINUE_WITH.format(name=name))
        else:
            await storage.reset(message.from_id)
            await vk.answer(message, texts.MSG_CANCELLED)
        return

    if confirmed is None:
        await vk.answer(message, texts.PROMPT_SELECT_ACTION, keyboard=context_switch_keyboard())
        return

    pending = context.pending
    if pending is None:
        await vk.answer(message, texts.ERR_CONTEXT_LOST)
        await storage.reset(message.from_id)
        return
    await storage.reset(message.from_id)

    if pending.reservation_id is not None:
        client = Client(
            reservation_id=pending.reservation_id,
            buyer_id=pending.buyer_id,
            buyer_vk_id=pending.buyer_vk_id,
            buyer_name=pending.buyer_name,
        )
        if pending.receipt is not None:
            await storage.save(
                message.from_id, BotState.MAIN_MENU, Context(client=client, from_main_menu=True)
            )
            await payment.start(message, storage, client, pending.receipt)
        else:
            await show(message, storage, client)
        return

    # У нового клиента брони нет — создаём
    try:
        async with unit_of_work() as session:
            seller = await users.require_app_user(session, message.from_id)
            reservation = await reservations.create(session, pending.buyer_id, seller.id)
    except ServiceError as e:
        logger.error("Error creating reservation on context switch: %s", e)
        await vk.answer(message, texts.ERR_DB_CREATE_BOOKING_SHORT)
        return
    template = texts.MSG_NEW_BOOKING_NO_RES if pending.receipt else texts.MSG_NEW_BOOKING_CREATED
    await vk.answer(
        message,
        template.format(name=pending.buyer_name, id=reservation.id),
        keyboard=get_empty_keyboard(),
    )
    client = Client(
        reservation_id=reservation.id,
        buyer_id=pending.buyer_id,
        buyer_vk_id=pending.buyer_vk_id,
        buyer_name=pending.buyer_name,
    )
    await storage.save(message.from_id, BotState.AWAITING_ROW, Context(client=client))
