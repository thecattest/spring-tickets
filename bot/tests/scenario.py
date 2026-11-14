"""
Каркас тестов сценариев бота: настоящий Bot, Router, хендлеры, Postgres и Redis
(testcontainers); подменён только HTTP-клиент vkbottle — всё, что уходит в VK.

    async def test_x(bot):
        replies = await bot.send(SELLER, "/start")
        assert "..." in replies[-1]

Тест подаёт событие message_new так, как его отдал бы Long Poll, и проверяет
отправленные ботом сообщения (FakeVK.sent) и данные в базе.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any

from vkbottle import API, ABCHTTPClient
from vkbottle.bot import Bot
from vkbottle.exception_factory import ErrorHandler

from bot.fsm.storage import RedisStorage
from bot.router import Router


@dataclass
class Sent:
    """Сообщение, которое бот отправил через messages.send."""

    peer_id: int
    text: str
    keyboard: dict | None
    attachment: str | None

    @property
    def buttons(self) -> list[str]:
        """Подписи кнопок клавиатуры (пусто — клавиатуры нет)."""
        if not self.keyboard:
            return []
        return [
            button["action"].get("label", "")
            for row in self.keyboard.get("buttons", [])
            for button in row
        ]


@dataclass
class FakeVK(ABCHTTPClient):
    """
    Подделка VK API на уровне HTTP: отвечает на те методы, что вызывает бот
    (messages.send, users.get). Любой другой метод — ошибка теста: значит,
    бот начал ходить в VK по-новому, и подделку надо дополнить осознанно.
    """

    sent: list[Sent] = field(default_factory=list)
    # vk_id → (имя, фамилия) для users.get
    users: dict[int, tuple[str, str]] = field(default_factory=dict)

    async def request_text(self, url: str, method: str = "GET", data: Any = None, **kwargs) -> str:
        name = url.rsplit("/", 1)[-1]
        data = data or {}
        if name == "messages.send":
            response = self._send(data)
        elif name == "users.get":
            response = self._users_get(data)
        else:
            raise AssertionError(f"Unexpected VK API call in test: {name} {data}")
        return json.dumps({"response": response})

    async def request_json(self, url: str, method: str = "GET", data: Any = None, **kwargs):
        return json.loads(await self.request_text(url, method, data, **kwargs))

    async def request_raw(self, *args, **kwargs):
        raise AssertionError("Unexpected raw HTTP request in test")

    async def request_content(self, *args, **kwargs):
        raise AssertionError("Unexpected content request in test")

    async def close(self) -> None:
        pass

    # Подмена bot.utils.attachments.reupload_attachments (скачивание с CDN VK
    # и повторная загрузка): запоминаем вызов, возвращаем строки вложений
    reuploaded: list[tuple[int, list[dict]]] = field(default_factory=list)

    async def reupload(self, api, attachment_urls: list[dict], peer_id: int) -> list[str]:
        self.reuploaded.append((peer_id, attachment_urls))
        return [f"photo{peer_id}_{i}" for i, _ in enumerate(attachment_urls, 1)]

    def _send(self, data: dict) -> Any:
        keyboard = data.get("keyboard")
        if isinstance(keyboard, str):
            keyboard = json.loads(keyboard)
        peer_ids = data.get("peer_ids")
        peers = (
            [int(p) for p in str(peer_ids).split(",")]
            if peer_ids is not None
            else [int(data["peer_id"])]
        )
        for peer in peers:
            self.sent.append(
                Sent(
                    peer_id=peer,
                    text=data.get("message", ""),
                    keyboard=keyboard,
                    attachment=data.get("attachment"),
                )
            )
        message_id = len(self.sent)
        if peer_ids is not None:
            return [
                {"peer_id": p, "message_id": message_id, "conversation_message_id": message_id}
                for p in peers
            ]
        return message_id

    def _users_get(self, data: dict) -> list[dict]:
        ids = [int(i) for i in str(data.get("user_ids", "")).split(",") if i]
        return [
            {
                "id": i,
                "first_name": self.users.get(i, ("Имя", str(i)))[0],
                "last_name": self.users.get(i, ("Имя", str(i)))[1],
            }
            for i in ids
        ]


def vk_message(
    from_id: int,
    text: str = "",
    *,
    fwd_from: int | None = None,
    reply_from: int | None = None,
    attachments: list | None = None,
    fwd_attachments: list | None = None,
    message_id: int = 1,
) -> dict:
    """Объект сообщения в формате VK API (для fwd_messages и reply_message тоже)."""
    msg: dict[str, Any] = {
        "id": message_id,
        "date": int(time.time()),
        "peer_id": from_id,
        "from_id": from_id,
        "text": text,
        "out": 0,
        "conversation_message_id": message_id,
        "fwd_messages": [],
        "attachments": attachments or [],
        "important": False,
        "is_hidden": False,
        "version": 1,
    }
    if fwd_from is not None:
        msg["fwd_messages"] = [
            {
                "date": int(time.time()) - 60,
                "from_id": fwd_from,
                "text": "сообщение покупателя",
                "attachments": fwd_attachments or [],
                "conversation_message_id": 1,
                "id": 0,
                "peer_id": fwd_from,
            }
        ]
    if reply_from is not None:
        msg["reply_message"] = {
            "date": int(time.time()) - 60,
            "from_id": reply_from,
            "text": "сообщение покупателя",
            "attachments": [],
            "conversation_message_id": 1,
            "id": 0,
            "peer_id": reply_from,
        }
    return msg


class BotHarness:
    def __init__(self, storage: RedisStorage):
        self.vk = FakeVK()
        self.storage = storage
        api = API("vk1.a.test", http_client=self.vk)
        # raise_exceptions: упавший хендлер роняет тест (по умолчанию vkbottle
        # только пишет исключение в лог и продолжает)
        self.bot = Bot(
            api=api,
            state_dispenser=storage,
            error_handler=ErrorHandler(raise_exceptions=True),
        )
        router = Router(storage=storage)
        router.register_all()
        self.bot.labeler.load(router.labeler)
        self._message_id = 0

    async def send(self, from_id: int, text: str = "", **kwargs) -> list[Sent]:
        """
        Подать сообщение от from_id так, как его отдал бы Long Poll.
        Возвращает сообщения, отправленные ботом в ответ (в любой чат).
        """
        self._message_id += 1
        before = len(self.vk.sent)
        event = {
            "type": "message_new",
            "event_id": f"test{self._message_id}",
            "v": "5.199",
            "group_id": 1,
            "object": {
                "message": vk_message(from_id, text, message_id=self._message_id, **kwargs),
                "client_info": {
                    "button_actions": ["text", "callback"],
                    "keyboard": True,
                    "inline_keyboard": True,
                    "carousel": True,
                    "lang_id": 0,
                },
            },
        }
        await self.bot.process_event(event)
        return self.vk.sent[before:]

    async def state(self, peer_id: int) -> str | None:
        """Текущее FSM-состояние пользователя (строкой) или None."""
        peer = await self.storage.get(peer_id)
        return None if peer is None else str(peer.state)


def photo(owner_id: int, photo_id: int = 1) -> dict:
    """Вложение-фото (чек об оплате) в формате VK API."""
    return {
        "type": "photo",
        "photo": {
            "id": photo_id,
            "owner_id": owner_id,
            "album_id": -3,
            "date": int(time.time()) - 60,
            "access_key": "key",
            "sizes": [
                {
                    "type": "x",
                    "url": f"https://sun.userapi.com/photo{photo_id}.jpg",
                    "width": 604,
                    "height": 800,
                }
            ],
        },
    }
