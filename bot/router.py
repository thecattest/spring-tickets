"""
Centralized handler registration for the VK bot.

Registration order enforced by register_all():
  1. Forwarded handler  — catches forwarded messages (any state, checked first)
  2. Command handlers   — text-matched commands (/start, /help, /cancel, etc.)
  3. State handlers     — FSM state-specific handlers (AWAITING_ROW, MAIN_MENU, etc.)

Order matters: vkbottle dispatches to the first matching blocking handler.
Commands must be registered BEFORE state handlers so that e.g. /cancel typed
while in AWAITING_ROW is intercepted by the command handler rather than falling
through to the state handler.

Storage injection:
  Handlers that accept (message, storage) are wrapped via _wrap() into
  (message,)-only closures that close over self.storage.
  Handlers that accept only (message,) are registered directly — no wrap.
"""

import logging
from vkbottle.framework.labeler.bot import BotLabeler
from vkbottle.bot import Message

from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage

logger = logging.getLogger(__name__)


class Router:
    """
    Centralizes all message handler registrations into a single BotLabeler.

    Usage::

        router = Router(storage)
        router.register_all()
        bot.labeler.load(router.labeler)
    """

    def __init__(self, storage: RedisStorage):
        self.labeler = BotLabeler()
        self.storage = storage

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_all(self) -> None:
        """
        Register all handlers in enforced dispatch order.

        Order:
          1. Forwarded message handler
          2. Command handlers
          3. FSM state handlers
        """
        self._register_forwarded()
        self._register_commands()
        self._register_states()

        count = len(self.labeler.message_view.handlers)
        logger.info(f"Router: {count} handlers registered")

    # ------------------------------------------------------------------
    # Storage injection wrapper
    # ------------------------------------------------------------------

    def _wrap(self, handler_func):
        """
        Wrap a (message, storage) handler into a (message,)-only coroutine.

        The returned closure closes over self.storage, allowing vkbottle to
        call it with a single Message argument while still providing storage
        to the underlying handler.

        Args:
            handler_func: Async function with signature (message, storage).

        Returns:
            Async function with signature (message,).
        """
        storage = self.storage

        async def wrapped(message: Message):
            await handler_func(message, storage)

        wrapped.__name__ = handler_func.__name__ + "_wrapped"
        return wrapped

    # ------------------------------------------------------------------
    # Registration groups
    # ------------------------------------------------------------------

    def _register_forwarded(self) -> None:
        """
        Register the forwarded message handler.

        Matches any message with fwd_messages — forwarded messages indicate
        a new client interaction initiated by the seller.
        """
        from bot.handlers.reservation import forwarded_message_handler

        self.labeler.message(
            func=lambda msg: bool(msg.fwd_messages)
        )(self._wrap(forwarded_message_handler))

    def _register_commands(self) -> None:
        """
        Register text-command handlers.

        Commands are registered BEFORE state handlers so that commands typed
        in any FSM state (e.g. /cancel while in AWAITING_SEATS) are caught
        by command handlers first.

        Handler signatures:
          start_handler(message)            — no storage needed
          help_handler(message)             — no storage needed
          cancel_handler(message, storage)  — needs storage to clear state
          reserve_command_handler(message, storage) — needs storage to set state
          debtors_command_handler(message)  — stateless, no storage
          refresh_debtors_handler(message)  — stateless, no storage
        """
        from bot.handlers.commands import start_handler, help_handler, cancel_handler
        from bot.handlers.reserve import reserve_command_handler
        from bot.handlers.debtors import debtors_command_handler, refresh_debtors_handler

        # /start — direct registration (no storage needed)
        self.labeler.message(text="/start")(start_handler)

        # /help and /Справка — direct registration
        self.labeler.message(text=["/help", "/Справка"])(help_handler)

        # /cancel and /Отмена — needs storage to clear FSM state
        self.labeler.message(text=["/cancel", "/Отмена"])(self._wrap(cancel_handler))

        # /reserve and /Резерв — needs storage to set RESERVE_ACTION state
        self.labeler.message(text=["/reserve", "/Резерв"])(self._wrap(reserve_command_handler))

        # /debtors and /Должники — stateless, direct registration
        self.labeler.message(text=["/debtors", "/Должники"])(debtors_command_handler)

        # "Обновить" button — stateless refresh of debtor list
        self.labeler.message(text="Обновить")(refresh_debtors_handler)

    def _register_states(self) -> None:
        """
        Register FSM state handlers.

        All state handlers accept (message, storage) and are wrapped via _wrap().
        States are listed in the order they appear in the BotState enum.
        IDLE is handled by the forwarded message handler above.
        """
        from bot.handlers.reservation import (
            awaiting_row_handler,
            awaiting_seats_handler,
            seat_addition_menu_handler,
        )
        from bot.handlers.menu import (
            main_menu_handler,
            context_switch_handler,
        )
        from bot.handlers.deletion import (
            deleting_row_handler,
            deleting_seats_handler,
            deletion_confirm_handler,
            cancel_confirm_handler,
        )
        from bot.handlers.payment import payment_quantity_handler
        from bot.handlers.reserve import (
            reserve_action_handler,
            reserve_adding_row_handler,
            reserve_adding_seats_handler,
            reserve_comment_handler,
            reserve_removing_row_handler,
            reserve_removing_seats_handler,
            reserve_remove_confirm_handler,
        )

        states = [
            # Reservation creation flow
            (BotState.AWAITING_ROW, awaiting_row_handler),
            (BotState.AWAITING_SEATS, awaiting_seats_handler),
            (BotState.SEAT_ADDITION_MENU, seat_addition_menu_handler),
            # Main menu and navigation
            (BotState.MAIN_MENU, main_menu_handler),
            (BotState.CONTEXT_SWITCH_CONFIRM, context_switch_handler),
            # Deletion flow
            (BotState.DELETING_ROW, deleting_row_handler),
            (BotState.DELETING_SEATS, deleting_seats_handler),
            (BotState.DELETION_CONFIRM, deletion_confirm_handler),
            (BotState.CANCEL_CONFIRM, cancel_confirm_handler),
            # Payment flow
            (BotState.PAYMENT_QUANTITY, payment_quantity_handler),
            # Reserve flow (admin only)
            (BotState.RESERVE_ACTION, reserve_action_handler),
            (BotState.RESERVE_ADDING_ROW, reserve_adding_row_handler),
            (BotState.RESERVE_ADDING_SEATS, reserve_adding_seats_handler),
            (BotState.RESERVE_COMMENT, reserve_comment_handler),
            (BotState.RESERVE_REMOVING_ROW, reserve_removing_row_handler),
            (BotState.RESERVE_REMOVING_SEATS, reserve_removing_seats_handler),
            (BotState.RESERVE_REMOVE_CONFIRM, reserve_remove_confirm_handler),
        ]

        for state, handler_func in states:
            self.labeler.message(state=state)(self._wrap(handler_func))
