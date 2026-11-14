"""
Declarative FSM configuration — single source of truth for all state behavior.

Each BotState has exactly one StateConfig entry describing:
- what input triggers the state's handler (text message, forwarded message, or button press)
- who is authorized to reach this state (any user, seller, or admin)
- where /cancel navigates back to (resolved by Phase 12)
- which states this state can transition forward into (informational)

Phase 10 Router reads FSM_CONFIG to auto-register vkbottle handlers.
Phase 12 /cancel reads back_state for step-back navigation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from tickets.bot.fsm.states import BotState


@dataclass
class StateConfig:
    """Configuration for a single FSM state."""

    state: BotState
    """Which state this entry configures."""

    input_type: Literal["text", "forwarded", "button"]
    """What kind of incoming message triggers this state's handler."""

    auth_guard: Literal["any", "seller", "admin"]
    """Minimum role required to reach this state."""

    handler: Callable | None = None
    """Actual handler function — left None in Phase 9. Phase 10 Router wires handlers."""

    back_state: BotState | None = None
    """State to return to on /cancel. Phase 12 resolves ambiguous cases via context."""

    forward_states: list[BotState] = field(default_factory=list)
    """States this state can transition into. Informational — not enforced by router."""


# handler fields left as None — Phase 10 Router wires handlers.
FSM_CONFIG: dict[BotState, StateConfig] = {
    BotState.IDLE: StateConfig(
        state=BotState.IDLE,
        input_type="forwarded",
        auth_guard="any",
        back_state=None,
        forward_states=[
            BotState.AWAITING_ROW,
            BotState.MAIN_MENU,
            BotState.CONTEXT_SWITCH_CONFIRM,
        ],
    ),
    BotState.AWAITING_ROW: StateConfig(
        state=BotState.AWAITING_ROW,
        input_type="text",
        auth_guard="seller",
        back_state=BotState.IDLE,  # NOTE: ambiguous — also reachable from SEAT_ADDITION_MENU. Phase 12 resolves via context.
        forward_states=[BotState.AWAITING_SEATS],
    ),
    BotState.AWAITING_SEATS: StateConfig(
        state=BotState.AWAITING_SEATS,
        input_type="text",
        auth_guard="seller",
        back_state=BotState.AWAITING_ROW,
        forward_states=[BotState.SEAT_ADDITION_MENU],
    ),
    BotState.SEAT_ADDITION_MENU: StateConfig(
        state=BotState.SEAT_ADDITION_MENU,
        input_type="button",
        auth_guard="seller",
        back_state=BotState.AWAITING_ROW,
        forward_states=[
            BotState.AWAITING_ROW,
            BotState.MAIN_MENU,
            BotState.IDLE,
        ],
    ),
    BotState.MAIN_MENU: StateConfig(
        state=BotState.MAIN_MENU,
        input_type="button",
        auth_guard="seller",
        back_state=BotState.IDLE,
        forward_states=[
            BotState.AWAITING_ROW,
            BotState.DELETING_ROW,
            BotState.CANCEL_CONFIRM,
            BotState.PAYMENT_QUANTITY,
        ],
    ),
    BotState.DELETING_ROW: StateConfig(
        state=BotState.DELETING_ROW,
        input_type="text",
        auth_guard="seller",
        back_state=BotState.MAIN_MENU,
        forward_states=[BotState.DELETING_SEATS],
    ),
    BotState.DELETING_SEATS: StateConfig(
        state=BotState.DELETING_SEATS,
        input_type="text",
        auth_guard="seller",
        back_state=BotState.DELETING_ROW,
        forward_states=[BotState.DELETION_CONFIRM],
    ),
    BotState.DELETION_CONFIRM: StateConfig(
        state=BotState.DELETION_CONFIRM,
        input_type="button",
        auth_guard="seller",
        back_state=BotState.DELETING_ROW,
        forward_states=[BotState.MAIN_MENU],
    ),
    BotState.CANCEL_CONFIRM: StateConfig(
        state=BotState.CANCEL_CONFIRM,
        input_type="button",
        auth_guard="seller",
        back_state=BotState.MAIN_MENU,
        forward_states=[BotState.IDLE, BotState.MAIN_MENU],
    ),
    BotState.CONTEXT_SWITCH_CONFIRM: StateConfig(
        state=BotState.CONTEXT_SWITCH_CONFIRM,
        input_type="button",
        auth_guard="any",
        back_state=None,
        forward_states=[BotState.MAIN_MENU, BotState.AWAITING_ROW],
    ),
    BotState.PAYMENT_QUANTITY: StateConfig(
        state=BotState.PAYMENT_QUANTITY,
        input_type="button",
        auth_guard="seller",
        back_state=BotState.MAIN_MENU,
        forward_states=[BotState.MAIN_MENU],
    ),
    BotState.RESERVE_ACTION: StateConfig(
        state=BotState.RESERVE_ACTION,
        input_type="button",
        auth_guard="admin",
        back_state=BotState.IDLE,
        forward_states=[BotState.RESERVE_ADDING_ROW, BotState.RESERVE_REMOVING_ROW],
    ),
    BotState.RESERVE_ADDING_ROW: StateConfig(
        state=BotState.RESERVE_ADDING_ROW,
        input_type="text",
        auth_guard="admin",
        back_state=BotState.RESERVE_ACTION,
        forward_states=[BotState.RESERVE_ADDING_SEATS],
    ),
    BotState.RESERVE_ADDING_SEATS: StateConfig(
        state=BotState.RESERVE_ADDING_SEATS,
        input_type="text",
        auth_guard="admin",
        back_state=BotState.RESERVE_ADDING_ROW,
        forward_states=[BotState.RESERVE_COMMENT],
    ),
    BotState.RESERVE_COMMENT: StateConfig(
        state=BotState.RESERVE_COMMENT,
        input_type="text",
        auth_guard="admin",
        back_state=BotState.RESERVE_ADDING_ROW,
        forward_states=[BotState.RESERVE_ACTION],
    ),
    BotState.RESERVE_REMOVING_ROW: StateConfig(
        state=BotState.RESERVE_REMOVING_ROW,
        input_type="text",
        auth_guard="admin",
        back_state=BotState.RESERVE_ACTION,
        forward_states=[BotState.RESERVE_REMOVING_SEATS],
    ),
    BotState.RESERVE_REMOVING_SEATS: StateConfig(
        state=BotState.RESERVE_REMOVING_SEATS,
        input_type="text",
        auth_guard="admin",
        back_state=BotState.RESERVE_REMOVING_ROW,
        forward_states=[BotState.RESERVE_REMOVE_CONFIRM],
    ),
    BotState.RESERVE_REMOVE_CONFIRM: StateConfig(
        state=BotState.RESERVE_REMOVE_CONFIRM,
        input_type="button",
        auth_guard="admin",
        back_state=BotState.RESERVE_REMOVING_ROW,
        forward_states=[BotState.RESERVE_ACTION],
    ),
}
