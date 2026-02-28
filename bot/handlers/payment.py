"""
Payment flow handlers.

Handles:
- start_payment_flow: Shared entry point for both receipt and button flows
- payment_quantity_handler: Quantity selection and recording payment (PAYMENT_QUANTITY state)
"""

import logging
from datetime import datetime

from vkbottle.bot import Message

from bot.constants import Btn
from bot import texts
from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage
from bot.utils import db
from bot.keyboards import payment_quantity_keyboard, main_menu_keyboard, get_empty_keyboard
from bot.messages import format_payment_confirmation, format_reservation_seats
from models.base import SeatStatus
from bot.config import SEAT_PRICE

logger = logging.getLogger(__name__)


async def start_payment_flow(
    message: Message,
    storage: RedisStorage,
    reservation_id: int,
    buyer_display_name: str,
    vk_message_url: str = None,
    vk_message_ts: datetime = None,
    receipt_attachments: list[str] = None,
):
    """
    Shared entry point for payment flow (both receipt-forward and button flows).

    Shows current seat status and prompts seller to select quantity paid.

    Args:
        message: VK message
        storage: Redis storage instance
        reservation_id: Reservation ID to record payment for
        buyer_display_name: Display name of buyer
        vk_message_url: VK receipt message URL (None for button flow)
        vk_message_ts: VK receipt message timestamp (None for button flow)
    """
    try:
        seats = db.get_reservation_seats(reservation_id)
        booked_seats = [s for s in seats if s.status == SeatStatus.BOOKED]

        if len(booked_seats) == 0:
            await message.answer(
                texts.MSG_NO_SEATS_FOR_PAYMENT.format(name=buyer_display_name),
                keyboard=main_menu_keyboard()
            )
            return

        formatted_seats = format_reservation_seats(seats)

        prompt = (
            f"Бронь — {buyer_display_name}\n\n"
            f"{formatted_seats}\n\n"
            f"Сколько мест оплачено?"
        )
        await message.answer(prompt, keyboard=payment_quantity_keyboard(len(booked_seats)))

        # Preserve existing context, add payment-specific fields
        context = await storage.get_context(message.from_id)
        await storage.set(
            message.from_id,
            BotState.PAYMENT_QUANTITY,
            reservation_id=context.get("reservation_id", reservation_id),
            buyer_vk_user_id=context.get("buyer_vk_user_id"),
            buyer_vk_api_id=context.get("buyer_vk_api_id"),
            buyer_display_name=context.get("buyer_display_name", buyer_display_name),
            payment_vk_message_url=vk_message_url,
            payment_vk_message_ts=vk_message_ts.isoformat() if vk_message_ts else None,
            receipt_attachments=receipt_attachments or [],
        )

        logger.info(f"Started payment flow for reservation {reservation_id}")

    except db.DatabaseError as e:
        logger.error(f"Database error starting payment flow: {e}")
        await message.answer(
            texts.ERR_DB_LOAD_BOOKING,
            keyboard=main_menu_keyboard()
        )


async def payment_quantity_handler(message: Message, storage: RedisStorage):
    """
    Handle messages in PAYMENT_QUANTITY state.

    Processes quantity selection (numbered button, "Все N" button, or "Отмена").

    Args:
        message: VK message
        storage: Redis storage instance
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)

    reservation_id = context.get("reservation_id")
    buyer_display_name = context.get("buyer_display_name")
    buyer_vk_user_id = context.get("buyer_vk_user_id")
    buyer_vk_api_id = context.get("buyer_vk_api_id")
    payment_vk_message_url = context.get("payment_vk_message_url")
    payment_vk_message_ts_raw = context.get("payment_vk_message_ts")

    if not reservation_id:
        await message.answer(texts.ERR_CONTEXT_LOST)
        await storage.delete(message.from_id)
        return

    # "Отмена" button - return to main menu
    if text == Btn.CANCEL:
        from bot.handlers.menu import show_main_menu
        await show_main_menu(
            message, storage, reservation_id,
            buyer_vk_user_id, buyer_display_name, buyer_vk_api_id,
        )
        return

    # Parse quantity
    quantity = None

    if text.startswith(Btn.PAY_ALL_PREFIX):
        # "Все N" button — pay all booked seats
        try:
            quantity = int(text[len(Btn.PAY_ALL_PREFIX):])
        except ValueError:
            await message.answer(texts.PROMPT_SELECT_QUANTITY)
            return
    else:
        try:
            quantity = int(text)
        except ValueError:
            # Unknown text - re-prompt with current booked count
            try:
                seats = db.get_reservation_seats(reservation_id)
                booked_count = sum(1 for s in seats if s.status == SeatStatus.BOOKED)
                await message.answer(
                    texts.PROMPT_SELECT_QUANTITY,
                    keyboard=payment_quantity_keyboard(booked_count) if booked_count > 0 else main_menu_keyboard()
                )
            except db.DatabaseError:
                await message.answer(texts.PROMPT_SELECT_QUANTITY)
            return

    # Validate quantity >= 1
    if quantity < 1:
        try:
            seats = db.get_reservation_seats(reservation_id)
            booked_count = sum(1 for s in seats if s.status == SeatStatus.BOOKED)
            await message.answer(
                texts.PROMPT_MIN_QUANTITY,
                keyboard=payment_quantity_keyboard(booked_count) if booked_count > 0 else main_menu_keyboard()
            )
        except db.DatabaseError:
            await message.answer(texts.PROMPT_MIN_QUANTITY)
        return

    # Validate quantity <= available booked seats
    try:
        seats = db.get_reservation_seats(reservation_id)
        booked_seats = [s for s in seats if s.status == SeatStatus.BOOKED]

        if quantity > len(booked_seats):
            await message.answer(
                texts.ERR_QTY_EXCEEDS.format(available=len(booked_seats)),
                keyboard=payment_quantity_keyboard(len(booked_seats))
            )
            return

    except db.DatabaseError as e:
        logger.error(f"Database error fetching seats for validation: {e}")
        await message.answer(
            texts.ERR_DB_CHECK_SEATS,
            keyboard=main_menu_keyboard()
        )
        return

    # Record payment
    try:
        seller_id = db.get_seller_id(message.from_id)

        # Parse vk_message_ts from stored ISO string
        payment_vk_message_ts = None
        if payment_vk_message_ts_raw:
            try:
                payment_vk_message_ts = datetime.fromisoformat(payment_vk_message_ts_raw)
            except (ValueError, TypeError):
                payment_vk_message_ts = None

        payment, paid_seats = db.record_payment(
            reservation_id,
            quantity,
            seller_id,
            vk_message_url=payment_vk_message_url,
            vk_message_ts=payment_vk_message_ts,
        )

        # Fetch updated seats to get remaining
        all_seats = db.get_reservation_seats(reservation_id)
        remaining_booked = [s for s in all_seats if s.status == SeatStatus.BOOKED]

        confirmation = format_payment_confirmation(
            paid_seats, remaining_booked, payment.payment_amount, buyer_display_name
        )
        await message.answer(confirmation, keyboard=main_menu_keyboard())

        # Notify all admins about the payment
        try:
            seller_app_user = db.get_app_user_by_vk_id(message.from_id)
            seller_name = seller_app_user.display_name if seller_app_user else "—"
            admin_vk_ids = db.get_all_admin_vk_ids()
            receipt_attachments = context.get("receipt_attachments", [])
            notification_text = texts.MSG_PAYMENT_ADMIN_NOTIFICATION.format(
                buyer_name=buyer_display_name,
                seller_name=seller_name,
                seat_count=quantity,
                amount=int(payment.payment_amount),
            )
            attachment_str = ",".join(receipt_attachments) if receipt_attachments else None
            for admin_vk_id in admin_vk_ids:
                if admin_vk_id == message.from_id:
                    continue  # не уведомлять самого себя
                try:
                    await message.ctx_api.messages.send(
                        peer_id=admin_vk_id,
                        message=notification_text,
                        attachment=attachment_str,
                        random_id=0,
                    )
                except Exception as e:
                    logger.warning(f"Failed to notify admin {admin_vk_id}: {e}")
        except Exception as e:
            logger.warning(f"Failed to send admin notifications: {e}")

        # Return to MAIN_MENU state
        await storage.set(
            message.from_id,
            BotState.MAIN_MENU,
            reservation_id=reservation_id,
            buyer_vk_user_id=buyer_vk_user_id,
            buyer_vk_api_id=buyer_vk_api_id,
            buyer_display_name=buyer_display_name,
            from_main_menu=True,
        )

        logger.info(
            f"Payment recorded: reservation {reservation_id}, {quantity} seats, "
            f"remaining booked: {len(remaining_booked)}"
        )

    except db.InsufficientSeatsError as e:
        logger.warning(f"Insufficient seats for payment: requested {e.requested}, available {e.available}")
        await message.answer(
            texts.ERR_INSUFFICIENT_SEATS.format(requested=e.requested, available=e.available),
            keyboard=payment_quantity_keyboard(e.available) if e.available > 0 else main_menu_keyboard()
        )

    except db.DatabaseError as e:
        logger.error(f"Database error recording payment: {e}")
        await message.answer(
            texts.ERR_DB_RECORD_PAYMENT,
            keyboard=main_menu_keyboard()
        )
        # Return to MAIN_MENU on database error
        await storage.set(
            message.from_id,
            BotState.MAIN_MENU,
            reservation_id=reservation_id,
            buyer_vk_user_id=buyer_vk_user_id,
            buyer_vk_api_id=buyer_vk_api_id,
            buyer_display_name=buyer_display_name,
            from_main_menu=True,
        )
