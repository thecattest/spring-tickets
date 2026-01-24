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
    """

    # Default state: waiting for user action
    IDLE = "idle"

    # Reservation creation flow
    AWAITING_ROW = "awaiting_row"
    AWAITING_SEATS = "awaiting_seats"
    SEAT_ADDITION_MENU = "seat_addition_menu"

    # Future states (Phase 2+)
    # MAIN_MENU = "main_menu"
    # AWAITING_DELETE_ROW = "awaiting_delete_row"
    # AWAITING_DELETE_SEATS = "awaiting_delete_seats"
    # AWAITING_PAYMENT_AMOUNT = "awaiting_payment_amount"
