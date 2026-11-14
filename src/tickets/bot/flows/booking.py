"""
Бронь: билетёр присылает покупателя (пересылка, ответ, ссылка) → новая бронь
или меню существующей → ряд → места → «Добавить ещё» / «Готово».
"""

import logging

from vkbottle.bot import Message

from tickets.bot import auth, texts, vk
from tickets.bot.constants import Btn
from tickets.bot.flows import common, menu, payment
from tickets.bot.fsm.context import Client, Context, PendingSwitch, SavedState
from tickets.bot.fsm.states import BotState
from tickets.bot.fsm.storage import RedisStorage
from tickets.bot.keyboards import (
    context_switch_keyboard,
    get_empty_keyboard,
    seat_addition_menu_keyboard,
)
from tickets.bot.messages import generate_reservation_script
from tickets.db import unit_of_work
from tickets.formatting import format_seat_ranges, pluralize_seats
from tickets.hall import get_seat_count
from tickets.services import reservations, seats, users
from tickets.services.errors import ReservationNotActiveError, SeatOccupiedError, ServiceError

logger = logging.getLogger(__name__)


# --- вход: билетёр прислал покупателя ---------------------------------------


@auth.requires_registered()
async def on_buyer(message: Message, storage: RedisStorage) -> None:
    """
    Пересылка, ответ или ссылка на профиль. Билетёр свободен — бронь
    покупателя (новая или меню существующей; с чеком — сразу оплата).
    Занят другим клиентом — предложить переключиться.
    """
    try:
        incoming = await vk.incoming(message)
    except vk.BuyerNotFound as e:
        await vk.answer(message, str(e))
        return

    state, context = await storage.load(message.from_id)
    if state not in (None, BotState.IDLE):
        await _while_busy(message, storage, state, context, incoming)
        return

    try:
        async with unit_of_work() as session:
            buyer = await users.get_or_create_vk_user(
                session, incoming.buyer_vk_id, incoming.buyer_name
            )
            reservation = await reservations.get_active(session, buyer.id)
            is_new = reservation is None
            if is_new:
                seller = await users.require_app_user(session, message.from_id)
                reservation = await reservations.create(session, buyer.id, seller.id)
    except ServiceError as e:
        logger.error("Database error creating reservation: %s", e)
        await vk.answer(message, texts.ERR_DB_CREATE_BOOKING)
        return

    client = Client(
        reservation_id=reservation.id,
        buyer_id=buyer.id,
        buyer_vk_id=incoming.buyer_vk_id,
        buyer_name=incoming.buyer_name,
    )
    if is_new:
        await vk.answer(
            message, texts.MSG_NEW_BOOKING_CREATED.format(name=client.buyer_name, id=reservation.id)
        )
        await storage.save(message.from_id, BotState.AWAITING_ROW, Context(client=client))
    elif incoming.receipt is not None:
        await storage.save(
            message.from_id, BotState.MAIN_MENU, Context(client=client, from_main_menu=True)
        )
        await payment.start(message, storage, client, incoming.receipt)
    else:
        await menu.show(message, storage, client)


async def _while_busy(
    message: Message,
    storage: RedisStorage,
    state: BotState,
    context: Context,
    incoming: vk.Incoming,
) -> None:
    current = context.client
    same = current is not None and current.buyer_vk_id == incoming.buyer_vk_id
    current_name = current.buyer_name if current else "текущего клиента"

    if same:
        if incoming.receipt is not None:
            if state != BotState.MAIN_MENU:
                await storage.save(
                    message.from_id,
                    BotState.MAIN_MENU,
                    Context(client=current, from_main_menu=True),
                )
            await payment.start(message, storage, current, incoming.receipt)
        elif state == BotState.MAIN_MENU:
            await menu.show(message, storage, current)
        else:
            await vk.answer(message, texts.ERR_ALREADY_WORKING)
        return

    if state != BotState.MAIN_MENU:
        prompt = texts.MSG_SWITCH_TO_CLIENT.format(name=incoming.buyer_name, current=current_name)
    elif incoming.receipt is not None:
        prompt = texts.MSG_SWITCH_RECEIPT.format(name=incoming.buyer_name, current=current_name)
    else:
        prompt = texts.MSG_SWITCH_PLAIN.format(current=current_name, name=incoming.buyer_name)

    try:
        async with unit_of_work() as session:
            buyer = await users.get_or_create_vk_user(
                session, incoming.buyer_vk_id, incoming.buyer_name
            )
            existing = await reservations.get_active(session, buyer.id)
    except ServiceError as e:
        logger.error("Database error checking reservation: %s", e)
        await vk.answer(message, texts.ERR_DB_CHECK_BOOKING)
        return

    await vk.answer(message, prompt, keyboard=context_switch_keyboard())
    switch = Context(
        pending=PendingSwitch(
            buyer_id=buyer.id,
            buyer_vk_id=incoming.buyer_vk_id,
            buyer_name=incoming.buyer_name,
            reservation_id=existing.id if existing else None,
            receipt=incoming.receipt,
        ),
        saved=SavedState(state=state, context=context),
    )
    await storage.save(message.from_id, BotState.CONTEXT_SWITCH_CONFIRM, switch)


# --- ряд и места ------------------------------------------------------------


async def on_row(message: Message, storage: RedisStorage) -> None:
    """AWAITING_ROW: номер ряда — в ряду есть свободные места."""
    parsed = common.parse_row(message.text)
    if not parsed.ok:
        await vk.answer(message, parsed.error)
        return
    row = parsed.value

    _, context = await storage.load(message.from_id)
    client = await common.require_client(message, storage, context, texts.ERR_CONTEXT_LOST_FWD)
    if client is None or not await common.require_active(message, storage, client):
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
        prompt = texts.MSG_ROW_SEAT_COUNT_WITH_OCCUPIED.format(
            row=row,
            seat_count=seat_count,
            seat_count_word=word,
            occupied=format_seat_ranges(occupied),
        )
    else:
        prompt = texts.MSG_ROW_SEAT_COUNT.format(
            row=row, seat_count=seat_count, seat_count_word=word
        )
    await vk.answer(message, prompt)
    context.current_row = row
    await storage.save(message.from_id, BotState.AWAITING_SEATS, context)


async def on_seats(message: Message, storage: RedisStorage) -> None:
    """AWAITING_SEATS: места в выбранном ряду — добавить в бронь."""
    _, context = await storage.load(message.from_id)
    client = context.client
    row = context.current_row
    if client is None or row is None:
        await vk.answer(message, texts.ERR_CONTEXT_LOST_FWD)
        await storage.reset(message.from_id)
        return
    if not await common.require_active(message, storage, client):
        return

    parsed = await common.parse_seat_list(message.text, row, "availability")
    if not parsed.ok:
        await vk.answer(message, parsed.error)
        return
    seat_list = parsed.value

    try:
        async with unit_of_work() as session:
            seller = await users.require_app_user(session, message.from_id)
            await reservations.add_seats(session, client.reservation_id, row, seat_list, seller.id)
            total = len(await seats.of_reservation(session, client.reservation_id))
    except SeatOccupiedError as e:
        # Заняли параллельно — между проверкой ввода и записью
        await vk.answer(
            message, await common.seat_conflicts_text(e.conflicts, "Попробуйте другие места:")
        )
        return
    except ReservationNotActiveError:
        await common.require_active(message, storage, client)
        return
    except ServiceError as e:
        logger.error("Error adding seats: %s", e)
        await vk.answer(message, texts.ERR_DB_ADD_SEATS)
        return

    await vk.answer(
        message,
        texts.MSG_SEATS_ADDED.format(
            count=len(seat_list),
            count_word=pluralize_seats(len(seat_list)),
            row=row,
            seats=", ".join(map(str, seat_list)),
            total=total,
            total_word=pluralize_seats(total),
        ),
        keyboard=seat_addition_menu_keyboard(),
    )
    await storage.save(message.from_id, BotState.SEAT_ADDITION_MENU, context)


async def on_addition_menu(message: Message, storage: RedisStorage) -> None:
    """SEAT_ADDITION_MENU: «Добавить еще» — следующий ряд, «Готово» — текст для клиента."""
    _, context = await storage.load(message.from_id)
    text = message.text.strip()

    if text == Btn.ADD_MORE:
        await vk.answer(message, texts.PROMPT_ENTER_ROW, keyboard=get_empty_keyboard())
        await storage.save(message.from_id, BotState.AWAITING_ROW, context)
        return
    if text != Btn.DONE:
        await vk.answer(message, texts.PROMPT_SELECT_ACTION, keyboard=seat_addition_menu_keyboard())
        return

    client = await common.require_client(message, storage, context, texts.ERR_CONTEXT_LOST)
    if client is None or not await common.require_active(message, storage, client):
        return
    try:
        async with unit_of_work() as session:
            seat_list = await seats.of_reservation(session, client.reservation_id)
        if seat_list:
            script = generate_reservation_script(
                buyer_display_name=client.buyer_name, seats=seat_list
            )
            await vk.answer(message, script, keyboard=get_empty_keyboard())
    except ServiceError as e:
        logger.error("Error generating script: %s", e)
        await vk.answer(message, texts.ERR_DB_GENERATE_SCRIPT)

    if context.from_main_menu:
        await menu.show(message, storage, client)
    else:
        await storage.reset(message.from_id)
