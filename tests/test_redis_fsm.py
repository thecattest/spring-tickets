"""
Test Redis FSM storage integration with vkbottle.

Verifies that StatePeer objects are correctly stored and retrieved.
"""

import pytest
from vkbottle.dispatch.dispenser.builtin import StatePeer

from tickets.bot.fsm.states import BotState


@pytest.mark.asyncio
async def test_redis_state_peer_storage(redis_storage):
    """Test that RedisStorage properly stores and retrieves StatePeer objects."""
    # redis_storage — временный Redis из testcontainers (conftest.py), пустой
    storage = redis_storage
    try:
        peer_id = 999999  # Test user ID

        # Clean up any existing state
        await storage.delete(peer_id)

        # Test 1: get() returns None when no state exists
        result = await storage.get(peer_id)
        assert result is None, "Expected None for non-existent state"

        # Test 2: set() stores a StatePeer
        await storage.set(
            peer_id, BotState.AWAITING_ROW, reservation_id=123, buyer_name="Test User"
        )

        # Test 3: get() returns StatePeer object
        result = await storage.get(peer_id)
        assert result is not None, "Expected StatePeer object"
        assert isinstance(result, StatePeer), f"Expected StatePeer, got {type(result)}"
        assert result.peer_id == peer_id, f"Expected peer_id={peer_id}, got {result.peer_id}"
        assert result.state == "BotState:awaiting_row", (
            f"Expected state='BotState:awaiting_row', got {result.state}"
        )
        assert result.payload["reservation_id"] == 123, "Expected reservation_id in payload"
        assert result.payload["buyer_name"] == "Test User", "Expected buyer_name in payload"

        # Test 4: State has .state attribute (required by vkbottle)
        assert hasattr(result, "state"), "StatePeer must have .state attribute"
        assert result.state == "BotState:awaiting_row"

        # Test 5: Update state with preserved context
        await storage.set(
            peer_id,
            BotState.AWAITING_SEATS,
            reservation_id=123,
            buyer_name="Test User",
            current_row=5,
        )

        result = await storage.get(peer_id)
        assert result.state == "BotState:awaiting_seats"
        assert result.payload["reservation_id"] == 123, "Context should be preserved"
        assert result.payload["current_row"] == 5, "New context should be added"

        # Test 6: get_context() helper method
        context = await storage.get_context(peer_id)
        assert context["reservation_id"] == 123
        assert context["current_row"] == 5

        # Test 7: update_context() helper method
        await storage.update_context(peer_id, seats_added=10)
        result = await storage.get(peer_id)
        assert result.state == "BotState:awaiting_seats", "State should be preserved"
        assert result.payload["seats_added"] == 10, "Context should be updated"
        assert result.payload["reservation_id"] == 123, "Old context should be preserved"

        # Test 8: delete() removes state
        await storage.delete(peer_id)
        result = await storage.get(peer_id)
        assert result is None, "State should be deleted"

        print("✅ All Redis FSM integration tests passed!")

    finally:
        await storage.delete(peer_id)
