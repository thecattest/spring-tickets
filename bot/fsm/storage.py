"""
Redis-based FSM storage with permanent persistence.

Key pattern: bot:fsm:{vk_user_id}
No TTL: states persist until explicitly cleared
"""

import json
import logging
from typing import Optional, Any, Dict
from redis.asyncio import Redis
from vkbottle.dispatch.dispenser import StateDispenser

logger = logging.getLogger(__name__)


class RedisStorage(StateDispenser):
    """
    Redis storage for FSM states and context data.

    Features:
    - Permanent storage (no TTL)
    - JSON serialization for complex context
    - Atomic get/set operations
    - Manual cleanup only
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
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
        self.redis: Optional[Redis] = None

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

    def _make_key(self, vk_user_id: int) -> str:
        """
        Generate Redis key for user state.

        Args:
            vk_user_id: VK user ID

        Returns:
            Redis key string
        """
        return f"bot:fsm:{vk_user_id}"

    async def get(self, key: int) -> Optional[str]:
        """
        Get FSM state for user.

        Args:
            key: VK user ID

        Returns:
            Current state or None
        """
        if not self.redis:
            raise RuntimeError("Redis not connected")

        redis_key = self._make_key(key)
        data = await self.redis.get(redis_key)

        if data:
            try:
                parsed = json.loads(data)
                state = parsed.get("state")
                logger.debug(f"FSM get: {redis_key} -> {state}")
                return state
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in Redis key: {redis_key}")
                return None

        return None

    async def set(self, key: int, value: str):
        """
        Set FSM state for user.

        Args:
            key: VK user ID
            value: New state
        """
        if not self.redis:
            raise RuntimeError("Redis not connected")

        redis_key = self._make_key(key)

        # Preserve existing context
        existing_data = await self.redis.get(redis_key)
        context = {}

        if existing_data:
            try:
                parsed = json.loads(existing_data)
                context = parsed.get("context", {})
            except json.JSONDecodeError:
                logger.warning(f"Could not parse existing context for {redis_key}")

        # Update state
        new_data = {
            "state": value,
            "context": context,
        }

        await self.redis.set(redis_key, json.dumps(new_data))
        logger.info(f"FSM transition: {redis_key} -> {value}")

    async def delete(self, key: int):
        """
        Delete FSM state for user.

        Args:
            key: VK user ID
        """
        if not self.redis:
            raise RuntimeError("Redis not connected")

        redis_key = self._make_key(key)
        await self.redis.delete(redis_key)
        logger.info(f"FSM cleared: {redis_key}")

    async def get_context(self, vk_user_id: int) -> Dict[str, Any]:
        """
        Get context data for user.

        Args:
            vk_user_id: VK user ID

        Returns:
            Context dictionary
        """
        if not self.redis:
            raise RuntimeError("Redis not connected")

        redis_key = self._make_key(vk_user_id)
        data = await self.redis.get(redis_key)

        if data:
            try:
                parsed = json.loads(data)
                return parsed.get("context", {})
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in Redis key: {redis_key}")
                return {}

        return {}

    async def set_context(self, vk_user_id: int, context: Dict[str, Any]):
        """
        Set context data for user.

        Args:
            vk_user_id: VK user ID
            context: Context dictionary to store
        """
        if not self.redis:
            raise RuntimeError("Redis not connected")

        redis_key = self._make_key(vk_user_id)

        # Preserve existing state
        existing_data = await self.redis.get(redis_key)
        state = None

        if existing_data:
            try:
                parsed = json.loads(existing_data)
                state = parsed.get("state")
            except json.JSONDecodeError:
                logger.warning(f"Could not parse existing state for {redis_key}")

        # Update context
        new_data = {
            "state": state,
            "context": context,
        }

        await self.redis.set(redis_key, json.dumps(new_data))
        logger.debug(f"FSM context updated: {redis_key}")

    async def update_context(self, vk_user_id: int, **kwargs):
        """
        Update specific context fields for user.

        Args:
            vk_user_id: VK user ID
            **kwargs: Key-value pairs to update in context
        """
        context = await self.get_context(vk_user_id)
        context.update(kwargs)
        await self.set_context(vk_user_id, context)
