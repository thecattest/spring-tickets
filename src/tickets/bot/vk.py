"""
Всё, что связано с VK: разбор входящего (пересылка, ответ, ссылка на профиль),
имя пользователя через VK API, чеки во вложениях и отправка сообщений.

Отправка — только через answer() / send(): у каждого сообщения уникальный
random_id, и VK отбрасывает повтор при ретрае запроса (с random_id=0 защиты
от дублей нет).
"""

import logging
import random
from dataclasses import dataclass
from typing import Any

from vkbottle import ABCAPI
from vkbottle.bot import Message

from tickets.bot.fsm.context import Receipt
from tickets.bot.utils.attachments import get_attachment_urls
from tickets.bot.utils.vk_link import parse_vk_link
from tickets.time import from_unix

logger = logging.getLogger(__name__)


def new_random_id() -> int:
    return random.getrandbits(31)


async def answer(message: Message, text: str, keyboard: str | None = None) -> None:
    """
    Ответ в тот же диалог. message.answer() сам режет длинный текст на части
    и для каждой берёт random_id + номер части.
    """
    await message.answer(text, keyboard=keyboard, random_id=new_random_id())


async def send(api: ABCAPI, peer_id: int, text: str, attachment: str | None = None) -> None:
    """Сообщение в другой диалог (уведомления админам)."""
    await api.messages.send(
        peer_id=peer_id, message=text, attachment=attachment, random_id=new_random_id()
    )


# --- входящее: кто покупатель ----------------------------------------------


class BuyerNotFound(Exception):
    """Покупателя по ссылке не нашли; текст — для билетёра."""


@dataclass
class Incoming:
    """Покупатель из сообщения билетёра (пересылка, ответ или ссылка)."""

    buyer_vk_id: int
    buyer_name: str
    receipt: Receipt | None  # в пересланном сообщении чек (фото или документ)


def forwarded_or_reply(message: Message) -> Any | None:
    """Пересланное сообщение или то, на которое ответили."""
    if message.fwd_messages:
        return message.fwd_messages[0]
    return message.reply_message


def mentions_buyer(message: Message) -> bool:
    """Сообщение про покупателя: пересылка, ответ или ссылка на профиль."""
    return bool(message.fwd_messages or message.reply_message or parse_vk_link(message.text or ""))


def _receipt(forwarded: Any) -> Receipt | None:
    attachments = getattr(forwarded, "attachments", None) or []
    if not any(a.photo is not None or a.doc is not None for a in attachments):
        return None
    return Receipt(
        vk_message_ts=from_unix(forwarded.date) if forwarded.date else None,
        attachments=get_attachment_urls(forwarded),
    )


async def full_name(api: ABCAPI, vk_id: int | str) -> tuple[int, str] | None:
    """(VK ID, «Имя Фамилия») по id или короткому имени; None — нет такого."""
    users = await api.users.get(user_ids=[vk_id])
    if not users:
        return None
    return users[0].id, f"{users[0].first_name} {users[0].last_name}"


async def incoming(message: Message) -> Incoming:
    """
    Покупатель из сообщения билетёра.

    Ссылка на профиль в тексте важнее отправителя пересланного сообщения
    (переслали сообщение, но речь о другом человеке). Ссылку не нашли —
    BuyerNotFound с текстом для билетёра.
    """
    forwarded = forwarded_or_reply(message)
    link = parse_vk_link(message.text or "")
    receipt = _receipt(forwarded) if forwarded is not None else None

    if link:
        try:
            found = await full_name(message.ctx_api, link)
        except Exception as e:
            logger.warning("Failed to resolve VK link %r: %s", link, e)
            raise BuyerNotFound("Не удалось найти пользователя VK по ссылке.") from e
        if found is None:
            raise BuyerNotFound("Пользователь VK не найден.")
        return Incoming(buyer_vk_id=found[0], buyer_name=found[1], receipt=receipt)

    buyer_vk_id = forwarded.from_id
    try:
        found = await full_name(message.ctx_api, buyer_vk_id)
    except Exception as e:
        logger.warning("Failed to fetch VK user %s: %s", buyer_vk_id, e)
        found = None
    name = found[1] if found else f"VK User {buyer_vk_id}"
    return Incoming(buyer_vk_id=buyer_vk_id, buyer_name=name, receipt=receipt)
