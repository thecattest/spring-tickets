"""
Main menu and context switch handlers.

Handles:
- Main menu display and navigation
- Main menu button actions (Добавить, Удалить, Удалить все, Оплата)
- Context switch confirmation when seller switches between clients
"""

import logging

from vkbottle.bot import Message

from bot import texts
from bot.constants import Btn
from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage
from bot.keyboards import (
    confirmation_keyboard,
    context_switch_keyboard,
    get_empty_keyboard,
    main_menu_keyboard,
)
from bot.messages import format_reservation_seats
from bot.utils import db
from bot.utils.formatting import pluralize_seats
from models.base import SeatStatus

logger = logging.getLogger(__name__)


async def show_main_menu(
    message: Message,
    storage: RedisStorage,
    reservation_id: int,
    vk_user_id: int,
    buyer_display_name: str,
    buyer_vk_api_id: int,
):
    """
    Display main menu for existing reservation.

    Args:
        message: VK message
        storage: Redis storage instance
        reservation_id: Reservation ID
        vk_user_id: VK user internal ID (not vk_user_id!)
        buyer_display_name: Display name of buyer
        buyer_vk_api_id: VK API ID (from VK API, used for same-client detection)
    """
    try:
        # Fetch all seats for reservation
        seats = db.get_reservation_seats(reservation_id)

        # Format seats with status indicators
        formatted_seats = format_reservation_seats(seats)

        # Build main menu message
        menu_text = f"Бронь #{reservation_id} — {buyer_display_name}\n\n{formatted_seats}\n\nВыберите действие:"

        # Send with main menu keyboard
        await message.answer(menu_text, keyboard=main_menu_keyboard())

        # Set FSM state to MAIN_MENU with context
        await storage.set(
            message.from_id,
            BotState.MAIN_MENU,
            reservation_id=reservation_id,
            buyer_vk_user_id=vk_user_id,
            buyer_vk_api_id=buyer_vk_api_id,
            buyer_display_name=buyer_display_name,
            from_main_menu=True,
        )

        logger.info(f"Displayed main menu for reservation {reservation_id}")

    except db.DatabaseError as e:
        logger.error(f"Error displaying main menu: {e}")
        await message.answer(texts.ERR_DB_LOAD_BOOKING)


async def main_menu_handler(message: Message, storage: RedisStorage):
    """
    Handle button presses in MAIN_MENU state.

    Buttons:
    - "Добавить" - Transition to AWAITING_ROW
    - "Удалить" - Transition to DELETING_ROW
    - "Удалить все" - Transition to CANCEL_CONFIRM
    - "Оплата" - Show placeholder message (Phase 3)

    Args:
        message: VK message
        storage: Redis storage instance
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)
    reservation_id = context.get("reservation_id")
    buyer_display_name = context.get("buyer_display_name")

    if not reservation_id:
        await message.answer(texts.ERR_CONTEXT_LOST)
        await storage.delete(message.from_id)
        return

    if text == Btn.ADD:
        # Transition to AWAITING_ROW (preserve context including from_main_menu=True)
        await message.answer(texts.PROMPT_ENTER_ROW, keyboard=get_empty_keyboard())
        await storage.set(message.from_id, BotState.AWAITING_ROW, **context)

    elif text == Btn.DELETE:
        # Check if reservation has any seats
        try:
            seats = db.get_reservation_seats(reservation_id)

            if not seats:
                await message.answer(texts.ERR_NO_SEATS_TO_DELETE, keyboard=main_menu_keyboard())
                return

            # Transition to DELETING_ROW
            await message.answer(texts.PROMPT_ENTER_ROW_DELETE, keyboard=get_empty_keyboard())
            await storage.set(message.from_id, BotState.DELETING_ROW, **context)

        except db.DatabaseError as e:
            logger.error(f"Error checking seats for deletion: {e}")
            await message.answer(texts.ERR_DB_CHECK_SEATS, keyboard=main_menu_keyboard())

    elif text == Btn.DELETE_ALL:
        # Check if reservation has any seats
        try:
            seats = db.get_reservation_seats(reservation_id)

            if not seats:
                await message.answer(texts.ERR_NO_SEATS, keyboard=main_menu_keyboard())
                return

            # Count by status
            paid_count = sum(1 for s in seats if s.status == SeatStatus.PAID)
            booked_count = sum(1 for s in seats if s.status == SeatStatus.BOOKED)

            if paid_count > 0:
                # Has paid seats — check admin rights immediately
                is_admin = db.is_user_admin(message.from_id)
                if not is_admin:
                    await message.answer(
                        texts.ERR_PAID_CANCEL_ADMIN_ONLY, keyboard=main_menu_keyboard()
                    )
                    return
                # Admin — show confirmation with paid seats warning
                msg = (
                    f"Отменить бронь {buyer_display_name}?\n\n"
                    f"Всего: {len(seats)} {pluralize_seats(len(seats))} (бронь: {booked_count}, оплачено: {paid_count})\n\n"
                    f"В брони {paid_count} оплаченных {pluralize_seats(paid_count)}."
                )
            else:
                # No paid seats — simple confirmation
                msg = f"Отменить бронь {buyer_display_name}?\n\nВсего: {len(seats)} {pluralize_seats(len(seats))}"

            # Send confirmation
            await message.answer(msg, keyboard=confirmation_keyboard())

            # Transition to CANCEL_CONFIRM
            await storage.set(message.from_id, BotState.CANCEL_CONFIRM, **context)

        except db.DatabaseError as e:
            logger.error(f"Error checking seats for cancellation: {e}")
            await message.answer(texts.ERR_DB_CHECK_SEATS, keyboard=main_menu_keyboard())

    elif text == Btn.PAYMENT:
        # Show info message — actual payment flow starts when seller sends a receipt (photo/doc)
        await message.answer(texts.MSG_PAYMENT_SEND_RECEIPT, keyboard=main_menu_keyboard())

    else:
        # Unknown text - re-show keyboard
        await message.answer(texts.PROMPT_SELECT_ACTION, keyboard=main_menu_keyboard())


async def context_switch_handler(message: Message, storage: RedisStorage):
    """
    Handle context switch confirmation.

    Handles "Да" / "Нет" responses when seller attempts to switch between clients.

    Args:
        message: VK message
        storage: Redis storage instance
    """
    text = message.text.strip()
    context = await storage.get_context(message.from_id)

    # Extract pending switch info and original state
    pending_buyer_vk_id = context.get("pending_buyer_vk_id")
    pending_buyer_vk_api_id = context.get("pending_buyer_vk_api_id")
    pending_buyer_display_name = context.get("pending_buyer_display_name")
    pending_has_reservation = context.get("pending_has_reservation", False)
    pending_reservation_id = context.get("pending_reservation_id")
    original_state = context.get("original_state")
    original_context = context.get("original_context", {})

    if text == Btn.YES:
        # Clear FSM and switch to new client
        await storage.delete(message.from_id)

        # Extract receipt metadata
        pending_is_receipt = context.get("pending_is_receipt", False)
        pending_receipt_vk_message_ts = context.get("pending_receipt_vk_message_ts")

        if pending_has_reservation:
            if pending_is_receipt:
                # Receipt-triggered switch -> enter payment flow for new client
                await storage.set(
                    message.from_id,
                    BotState.MAIN_MENU,
                    reservation_id=pending_reservation_id,
                    buyer_vk_user_id=pending_buyer_vk_id,
                    buyer_vk_api_id=pending_buyer_vk_api_id,
                    buyer_display_name=pending_buyer_display_name,
                    from_main_menu=True,
                )
                from bot.handlers.payment import start_payment_flow

                vk_message_ts = None
                if pending_receipt_vk_message_ts:
                    from datetime import datetime

                    from timeutils import ensure_utc

                    try:
                        vk_message_ts = ensure_utc(
                            datetime.fromisoformat(pending_receipt_vk_message_ts)
                        )
                    except (ValueError, TypeError):
                        vk_message_ts = None
                await start_payment_flow(
                    message,
                    storage,
                    pending_reservation_id,
                    pending_buyer_display_name,
                    vk_message_url=None,
                    vk_message_ts=vk_message_ts,
                    receipt_attachments=context.get("pending_receipt_attachments", []),
                )
            else:
                # Normal switch -> show main menu for new client's existing reservation
                await show_main_menu(
                    message,
                    storage,
                    pending_reservation_id,
                    pending_buyer_vk_id,
                    pending_buyer_display_name,
                    pending_buyer_vk_api_id,
                )
        else:
            if pending_is_receipt:
                # Receipt from client with no reservation — can't record payment, create reservation
                try:
                    seller_id = db.get_seller_id(message.from_id)
                    reservation = db.create_reservation(pending_buyer_vk_id, seller_id)

                    await message.answer(
                        texts.MSG_NEW_BOOKING_NO_RES.format(
                            name=pending_buyer_display_name,
                            id=reservation.id,
                        ),
                        keyboard=get_empty_keyboard(),
                    )

                    await storage.set(
                        message.from_id,
                        BotState.AWAITING_ROW,
                        reservation_id=reservation.id,
                        buyer_vk_user_id=pending_buyer_vk_id,
                        buyer_display_name=pending_buyer_display_name,
                        buyer_vk_api_id=pending_buyer_vk_api_id,
                    )
                except db.DatabaseError as e:
                    logger.error(f"Error creating reservation on context switch: {e}")
                    await message.answer(texts.ERR_DB_CREATE_BOOKING_SHORT)
            else:
                # Normal switch with no reservation -> create new reservation
                try:
                    seller_id = db.get_seller_id(message.from_id)
                    reservation = db.create_reservation(pending_buyer_vk_id, seller_id)

                    await message.answer(
                        texts.MSG_NEW_BOOKING_CREATED.format(
                            name=pending_buyer_display_name,
                            id=reservation.id,
                        ),
                        keyboard=get_empty_keyboard(),
                    )

                    await storage.set(
                        message.from_id,
                        BotState.AWAITING_ROW,
                        reservation_id=reservation.id,
                        buyer_vk_user_id=pending_buyer_vk_id,
                        buyer_display_name=pending_buyer_display_name,
                        buyer_vk_api_id=pending_buyer_vk_api_id,
                    )

                except db.DatabaseError as e:
                    logger.error(f"Error creating reservation on context switch: {e}")
                    await message.answer(texts.ERR_DB_CREATE_BOOKING_SHORT)

    elif text == Btn.NO:
        # Restore previous state and context
        if original_state and original_state != "idle":
            restored_state = BotState(original_state.split(":")[-1])
            await storage.set(message.from_id, restored_state, **original_context)
            await message.answer(
                texts.MSG_CONTINUE_WITH.format(
                    name=original_context.get("buyer_display_name", "предыдущим клиентом")
                )
            )
        else:
            # No original state to restore - just clear
            await storage.delete(message.from_id)
            await message.answer(texts.MSG_CANCELLED)

    else:
        # Unknown response - re-show options
        await message.answer(texts.PROMPT_SELECT_ACTION, keyboard=context_switch_keyboard())
