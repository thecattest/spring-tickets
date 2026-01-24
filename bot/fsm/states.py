"""
FSM state definitions for the VK bot.

States represent different stages of the conversation flow.
All states are stored permanently in Redis (no TTL).
"""

from vkbottle import BaseStateGroup


class BotState(BaseStateGroup):
    """
    Bot conversation states.

    Flow for reservation creation:
    IDLE -> AWAITING_ROW -> AWAITING_SEATS -> SEAT_ADDITION_MENU -> IDLE

    Deletion flow:
    MAIN_MENU -> DELETING_ROW -> DELETING_SEATS -> DELETION_CONFIRM -> MAIN_MENU

    Cancel flow:
    MAIN_MENU -> CANCEL_CONFIRM -> IDLE

    Context switch:
    (any state) -> CONTEXT_SWITCH_CONFIRM -> (new client context)
    """

    # Default state: waiting for user action
    IDLE = "idle"

    # Reservation creation flow
    AWAITING_ROW = "awaiting_row"
    AWAITING_SEATS = "awaiting_seats"
    SEAT_ADDITION_MENU = "seat_addition_menu"

    # Main menu and deletion flow (Phase 2)
    MAIN_MENU = "main_menu"
    DELETING_ROW = "deleting_row"
    DELETING_SEATS = "deleting_seats"
    DELETION_CONFIRM = "deletion_confirm"
    CANCEL_CONFIRM = "cancel_confirm"
    CONTEXT_SWITCH_CONFIRM = "context_switch_confirm"

    # Future states (Phase 3+)
    # AWAITING_PAYMENT_AMOUNT = "awaiting_payment_amount"
