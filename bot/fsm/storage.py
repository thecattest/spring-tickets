"""
Redis-based FSM storage with permanent persistence.

Key pattern: bot:fsm:{peer_id}
No TTL: states persist until explicitly cleared
"""

import json
import logging
from typing import Any

from redis.asyncio import Redis
from vkbottle import BaseStateGroup
from vkbottle.dispatch.dispenser import ABCStateDispenser
from vkbottle.dispatch.dispenser.builtin import StatePeer

logger = logging.getLogger(__name__)


class RedisStorage(ABCStateDispenser):
    """
    Redis storage for FSM states using StatePeer objects.

    Features:
    - Permanent storage (no TTL)
    - Full StatePeer serialization (peer_id, state, payload)
    - Atomic get/set operations
    - Manual cleanup only

    Note: Uses StatePeer.payload for context data (replaces separate context storage)
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
    ):
        """
        Initialize Redis storage.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (optional)
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.redis: Redis | None = None

    async def connect(self):
        """
        Establish Redis connection.

        Raises:
            redis.exceptions.ConnectionError: If connection fails
        """
        self.redis = Redis(
            host=self.host,
            port=self.port,
            db=self.db,
            password=self.password,
            decode_responses=True,
        )
        # Test connection
        await self.redis.ping()
        logger.info(f"Redis connected: {self.host}:{self.port}/{self.db}")

    async def close(self):
        """
        Close Redis connection.
        """
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")

    def _make_key(self, peer_id: int) -> str:
        """
        Generate Redis key for peer state.

        Args:
            peer_id: VK peer ID (user ID)

        Returns:
            Redis key string
        """
        return f"bot:fsm:{peer_id}"

    async def get(self, peer_id: int) -> StatePeer | None:
        """
        Get StatePeer for user.

        Args:
            peer_id: VK peer ID (user ID)

        Returns:
            StatePeer object or None
        """
        if not self.redis:
            raise RuntimeError("Redis not connected")

        redis_key = self._make_key(peer_id)
        data = await self.redis.get(redis_key)

        if data:
            try:
                parsed = json.loads(data)

                # Migrate old format (pre-StatePeer) to new format
                if "peer_id" not in parsed:
                    logger.warning(f"Old format detected in {redis_key}, migrating...")
                    # Old format: {"state": "...", "context": {...}}
                    # New format: {"peer_id": X, "state": "...", "payload": {...}}
                    old_state = parsed.get("state")
                    old_context = parsed.get("context", {})

                    # Create StatePeer with migrated data
                    state_peer = StatePeer(
                        peer_id=peer_id,
                        state=old_state if old_state else "idle",
                        payload=old_context,
                    )

                    # Update Redis with new format
                    await self.redis.set(redis_key, json.dumps(state_peer.model_dump()))
                    logger.info(f"Migrated {redis_key} to StatePeer format")
                    return state_peer

                # New format - reconstruct StatePeer
                state_peer = StatePeer(**parsed)
                logger.debug(f"FSM get: {redis_key} -> {state_peer.state}")
                return state_peer
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.error(f"Failed to parse StatePeer from Redis key {redis_key}: {e}")
                # Clear corrupted data
                await self.redis.delete(redis_key)
                logger.warning(f"Cleared corrupted data from {redis_key}")
                return None

        return None

    async def set(self, peer_id: int, state: BaseStateGroup, **payload):
        """
        Set FSM state for user.

        Args:
            peer_id: VK peer ID (user ID)
            state: New state (BaseStateGroup attribute)
            **payload: Additional context data to store in StatePeer.payload
        """
        if not self.redis:
            raise RuntimeError("Redis not connected")

        redis_key = self._make_key(peer_id)

        # Create StatePeer object
        state_peer = StatePeer(peer_id=peer_id, state=state, payload=payload)

        # Serialize to JSON
        data = state_peer.model_dump()
        await self.redis.set(redis_key, json.dumps(data))

        logger.info(
            f"FSM transition: {redis_key} -> {state_peer.state} (payload: {len(payload)} keys)"
        )

    async def delete(self, peer_id: int):
        """
        Delete FSM state for user.

        Args:
            peer_id: VK peer ID (user ID)
        """
        if not self.redis:
            raise RuntimeError("Redis not connected")

        redis_key = self._make_key(peer_id)
        await self.redis.delete(redis_key)
        logger.info(f"FSM cleared: {redis_key}")

    # Helper methods for context access (using StatePeer.payload)

    async def get_context(self, peer_id: int) -> dict[str, Any]:
        """
        Get context data (payload) for user.

        Args:
            peer_id: VK peer ID (user ID)

        Returns:
            Payload dictionary from StatePeer
        """
        state_peer = await self.get(peer_id)
        return state_peer.payload if state_peer else {}

    async def update_context(self, peer_id: int, **kwargs):
        """
        Update specific context fields for user.

        Preserves existing state and merges new payload data.

        Args:
            peer_id: VK peer ID (user ID)
            **kwargs: Key-value pairs to update in payload
        """
        # Get existing StatePeer
        state_peer = await self.get(peer_id)

        if not state_peer:
            logger.warning(f"Cannot update context for {peer_id}: no state found")
            return

        # Merge payload
        updated_payload = {**state_peer.payload, **kwargs}

        # Set with updated payload, preserving state
        await self.set(peer_id, state_peer.state, **updated_payload)
