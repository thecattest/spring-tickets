"""Состояние FSM из строки Redis: storage.parse_state."""

import pytest

from tickets.bot.fsm.states import BotState
from tickets.bot.fsm.storage import parse_state


@pytest.mark.parametrize("state", list(BotState))
def test_every_state_round_trips(state):
    # str(state) — как vkbottle пишет состояние в StatePeer: 'BotState:main_menu'
    assert parse_state(str(state)) == state
    assert parse_state(state.value) == state


@pytest.mark.parametrize("raw", [None, "", "BotState:no_such_state", "garbage"])
def test_unknown_or_empty_is_none(raw):
    assert parse_state(raw) is None
