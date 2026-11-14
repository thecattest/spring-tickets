"""
Технические уведомления владельцам проекта (OWNER_VK_IDS) в VK: падения
задач, файлы бэкапов, позже — ошибки бота и веба, watchdog.

Работает из любого процесса: свой клиент VK API с токеном сообщества,
без запущенного бота. Никогда не бросает исключений — уведомление не должно
ломать то, о чём уведомляет; неудача только пишется в лог.

На этапе 7 переезжает в tickets/notify.py; там же — ограничение частоты
одинаковых сообщений через Redis.
"""

import logging
import random
from pathlib import Path

from pydantic import ValidationError
from vkbottle import API, DocMessagesUploader

from config import VkSettings, vk_settings

logger = logging.getLogger(__name__)

# Лимит длины сообщения VK — 4096 символов
MAX_TEXT = 4000


async def notify_owner(text: str, *, file: Path | None = None) -> None:
    """Отправить сообщение (и файл документом) каждому владельцу."""
    try:
        vk = vk_settings()
    except ValidationError:
        # В процессе нет настроек VK (например, migrate) — уведомлять нечем
        logger.warning("notify_owner: VK settings are not configured, not sent: %s", text)
        return
    if not vk.owner_vk_ids:
        logger.warning("notify_owner: OWNER_VK_IDS is empty, not sent: %s", text)
        return

    if len(text) > MAX_TEXT:
        text = text[: MAX_TEXT - 1] + "…"

    try:
        await _send_all(vk, text, file)
    except Exception:
        logger.exception("notify_owner: unexpected error")


async def _send_all(vk: VkSettings, text: str, file: Path | None) -> None:
    api = API(vk.vk_bot_token.get_secret_value())
    try:
        for owner_id in vk.owner_vk_ids:
            try:
                attachment = None
                if file is not None:
                    # Загрузка документа привязана к получателю — для каждого своя
                    attachment = await DocMessagesUploader(api).upload(
                        file_source=str(file), peer_id=owner_id, title=file.name
                    )
                # VK отбрасывает повтор с тем же random_id (например, ретрай
                # запроса после таймаута); с random_id=0 защиты от дублей нет
                await api.messages.send(
                    peer_id=owner_id,
                    message=text,
                    attachment=attachment,
                    random_id=random.getrandbits(31),
                )
            except Exception:
                logger.exception("notify_owner: failed to send to %s", owner_id)
    finally:
        await api.http_client.close()
