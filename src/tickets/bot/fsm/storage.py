"""
FSM в Redis: состояние и контекст диалога на пользователя, ключ bot:fsm:{peer_id}.

Без TTL: состояние живёт, пока его не сбросят. Формат значения — StatePeer
vkbottle ({peer_id, state, payload}): по state vkbottle выбирает хендлер, в
payload — Context (tickets.bot.fsm.context) в JSON.

Сценарии работают через load() / save() / reset(); get() / set() / delete() —
интерфейс ABCStateDispenser для vkbottle.
"""

import json
import logging

from pydantic import ValidationError
from redis.asyncio import Redis
from vkbottle import BaseStateGroup
from vkbottle.dispatch.dispenser import ABCStateDispenser
from vkbottle.dispatch.dispenser.builtin import StatePeer

from tickets.bot.fsm.context import Context
from tickets.bot.fsm.states import BotState

logger = logging.getLogger(__name__)


def parse_state(raw: str | None) -> BotState | None:
    """'BotState:main_menu' (так vkbottle хранит состояние) или 'main_menu' → BotState."""
    if not raw:
        return None
    try:
        return BotState(raw.split(":")[-1])
    except ValueError:
        return None


class RedisStorage(ABCStateDispenser):
    def __init__(
        self, host: str = "localhost", port: int = 6379, db: int = 0, password: str | None = None
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.redis: Redis | None = None

    async def connect(self) -> None:
        self.redis = Redis(
            host=self.host,
            port=self.port,
            db=self.db,
            password=self.password,
            decode_responses=True,
        )
        await self.redis.ping()
        logger.info("Redis connected: %s:%s/%s", self.host, self.port, self.db)

    async def close(self) -> None:
        if self.redis:
            await self.redis.aclose()
            logger.info("Redis connection closed")

    def _key(self, peer_id: int) -> str:
        return f"bot:fsm:{peer_id}"

    def _redis(self) -> Redis:
        if not self.redis:
            raise RuntimeError("Redis not connected")
        return self.redis

    # --- ABCStateDispenser (vkbottle) ---------------------------------------

    async def get(self, peer_id: int) -> StatePeer | None:
        data = await self._redis().get(self._key(peer_id))
        if not data:
            return None
        try:
            return StatePeer(**json.loads(data))
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error("Unreadable FSM state for %s, reset: %s", peer_id, e)
            await self.delete(peer_id)
            return None

    async def set(self, peer_id: int, state: BaseStateGroup, **payload) -> None:
        peer = StatePeer(peer_id=peer_id, state=state, payload=payload)
        await self._redis().set(self._key(peer_id), json.dumps(peer.model_dump()))
        logger.info("FSM %s -> %s", peer_id, peer.state)

    async def delete(self, peer_id: int) -> None:
        await self._redis().delete(self._key(peer_id))
        logger.info("FSM %s cleared", peer_id)

    # --- для сценариев --------------------------------------------------------

    async def load(self, peer_id: int) -> tuple[BotState | None, Context]:
        """
        Состояние и контекст; нет — (None, пустой Context). Контекст не
        читается (формат сменился несовместимо) — лог и сброс: сценарий
        увидит пустой контекст и попросит начать заново.
        """
        peer = await self.get(peer_id)
        if peer is None:
            return None, Context()
        try:
            context = Context.model_validate(peer.payload)
        except ValidationError as e:
            logger.error("Unreadable FSM context for %s, reset: %s", peer_id, e)
            await self.delete(peer_id)
            return None, Context()
        return parse_state(peer.state), context

    async def save(self, peer_id: int, state: BotState, context: Context) -> None:
        await self.set(peer_id, state, **context.model_dump(mode="json"))

    async def reset(self, peer_id: int) -> None:
        await self.delete(peer_id)
