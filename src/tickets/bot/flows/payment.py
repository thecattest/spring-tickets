"""Оплата по чеку: сколько мест оплачено → запись оплаты → уведомление админам."""

import logging

from vkbottle.bot import Message

from tickets.bot import texts, vk
from tickets.bot.constants import Btn
from tickets.bot.flows import common, menu
from tickets.bot.fsm.context import Client, Context, Receipt
from tickets.bot.fsm.states import BotState
from tickets.bot.fsm.storage import RedisStorage
from tickets.bot.keyboards import main_menu_keyboard, payment_quantity_keyboard
from tickets.bot.messages import format_payment_confirmation, format_reservation_seats
from tickets.bot.utils import attachments
from tickets.db import unit_of_work
from tickets.formatting import pluralize_seats
from tickets.models.base import SeatStatus
from tickets.services import payments, seats, users
from tickets.services.errors import InsufficientSeatsError, ServiceError

logger = logging.getLogger(__name__)


async def _booked_count(client: Client) -> int:
    async with unit_of_work() as session:
        seat_list = await seats.of_reservation(session, client.reservation_id)
    return sum(1 for s in seat_list if s.status == SeatStatus.BOOKED)


def _quantity_keyboard(booked: int) -> str:
    return payment_quantity_keyboard(booked) if booked > 0 else main_menu_keyboard()


async def start(message: Message, storage: RedisStorage, client: Client, receipt: Receipt) -> None:
    """Пришёл чек: показать места и спросить, сколько оплачено."""
    try:
        async with unit_of_work() as session:
            seat_list = await seats.of_reservation(session, client.reservation_id)
    except ServiceError as e:
        logger.error("Database error starting payment flow: %s", e)
        await vk.answer(message, texts.ERR_DB_LOAD_BOOKING, keyboard=main_menu_keyboard())
        return
    booked = sum(1 for s in seat_list if s.status == SeatStatus.BOOKED)
    if booked == 0:
        await vk.answer(
            message,
            texts.MSG_NO_SEATS_FOR_PAYMENT.format(name=client.buyer_name),
            keyboard=main_menu_keyboard(),
        )
        return
    prompt = (
        f"Бронь — {client.buyer_name}\n\n{format_reservation_seats(seat_list)}"
        "\n\nСколько мест оплачено?"
    )
    await vk.answer(message, prompt, keyboard=payment_quantity_keyboard(booked))
    await storage.save(
        message.from_id, BotState.PAYMENT_QUANTITY, Context(client=client, receipt=receipt)
    )


def _parse_quantity(text: str) -> int | None:
    if text.startswith(Btn.PAY_ALL_PREFIX):  # кнопка «Все N»
        text = text[len(Btn.PAY_ALL_PREFIX) :]
    try:
        return int(text)
    except ValueError:
        return None


async def on_quantity(message: Message, storage: RedisStorage) -> None:
    """PAYMENT_QUANTITY: число мест (кнопка или ввод) или «Отмена»."""
    _, context = await storage.load(message.from_id)
    client = await common.require_client(message, storage, context, texts.ERR_CONTEXT_LOST)
    if client is None or not await common.require_active(message, storage, client):
        return
    text = message.text.strip()

    if text == Btn.CANCEL:
        await menu.show(message, storage, client)
        return

    quantity = _parse_quantity(text)
    if quantity is None or quantity < 1:
        prompt = texts.PROMPT_SELECT_QUANTITY if quantity is None else texts.PROMPT_MIN_QUANTITY
        await vk.answer(message, prompt, keyboard=_quantity_keyboard(await _booked_count(client)))
        return
    booked = await _booked_count(client)
    if quantity > booked:
        await vk.answer(
            message,
            texts.ERR_QTY_EXCEEDS.format(available=booked),
            keyboard=payment_quantity_keyboard(booked),
        )
        return

    # Чек — заново загружаем для диалогов с админами: сетевой вызов, до транзакции
    receipt = context.receipt or Receipt()
    attachment = None
    if receipt.attachments:
        try:
            uploaded = await attachments.reupload_attachments(
                message.ctx_api, receipt.attachments, peer_id=message.from_id
            )
            attachment = ",".join(uploaded) or None
        except Exception as e:
            logger.warning("Failed to reupload receipt attachments: %s", e)

    menu_context = Context(client=client, from_main_menu=True)
    try:
        async with unit_of_work() as session:
            seller = await users.require_app_user(session, message.from_id)
            payment, paid = await payments.record(
                session,
                client.reservation_id,
                quantity,
                seller.id,
                vk_message_ts=receipt.vk_message_ts,
                receipt_attachments=attachment,
            )
            remaining = [
                s
                for s in await seats.of_reservation(session, client.reservation_id)
                if s.status == SeatStatus.BOOKED
            ]
            admin_ids = await users.admin_vk_ids(session)
    except InsufficientSeatsError as e:
        await vk.answer(
            message,
            texts.ERR_INSUFFICIENT_SEATS.format(
                requested=e.requested,
                requested_word=pluralize_seats(e.requested),
                available=e.available,
            ),
            keyboard=_quantity_keyboard(e.available),
        )
        return
    except ServiceError as e:
        logger.error("Database error recording payment: %s", e)
        await vk.answer(message, texts.ERR_DB_RECORD_PAYMENT, keyboard=main_menu_keyboard())
        await storage.save(message.from_id, BotState.MAIN_MENU, menu_context)
        return

    await vk.answer(
        message,
        format_payment_confirmation(paid, remaining, payment.payment_amount, client.buyer_name),
        keyboard=main_menu_keyboard(),
    )
    await storage.save(message.from_id, BotState.MAIN_MENU, menu_context)
    logger.info("Payment recorded: reservation %s, %d seats", client.reservation_id, quantity)

    # После коммита: уведомить админов (кроме себя) — с тем же чеком
    notification = texts.MSG_PAYMENT_ADMIN_NOTIFICATION.format(
        buyer_name=client.buyer_name,
        buyer_vk_id=client.buyer_vk_id,
        seller_name=seller.display_name,
        seat_count=quantity,
        seat_count_word=pluralize_seats(quantity),
        amount=int(payment.payment_amount),
    )
    for admin_vk_id in admin_ids:
        if admin_vk_id == message.from_id:
            continue
        try:
            await vk.send(message.ctx_api, admin_vk_id, notification, attachment=attachment)
        except Exception as e:
            logger.warning("Failed to notify admin %s: %s", admin_vk_id, e)
