"""
Утилиты для работы с вложениями VK.

Предоставляет функции для извлечения URL вложений из пересланных сообщений
и их повторной загрузки через VK Upload API для отправки в другие диалоги.
"""

import logging

import aiohttp
from vkbottle import ABCAPI
from vkbottle.tools import PhotoMessageUploader, DocMessagesUploader

logger = logging.getLogger(__name__)


def get_attachment_urls(forwarded) -> list[dict]:
    """
    Извлечь URL вложений (фото/документы) из пересланного сообщения.

    Returns:
        Список словарей: [{"type": "photo"|"doc", "url": "...", "title": "..."}]
    """
    result = []
    if not hasattr(forwarded, "attachments") or not forwarded.attachments:
        return result
    for att in forwarded.attachments:
        if att.photo is not None:
            # Берём самый большой размер
            sizes = att.photo.sizes or []
            if sizes:
                best = max(sizes, key=lambda s: (s.width or 0) * (s.height or 0))
                url = best.url or best.src
                if url:
                    result.append({"type": "photo", "url": url, "title": "photo.jpg"})
        elif att.doc is not None:
            if att.doc.url:
                result.append({
                    "type": "doc",
                    "url": att.doc.url,
                    "title": att.doc.title or "document",
                })
    return result


async def reupload_attachments(
    api: ABCAPI,
    attachment_urls: list[dict],
    peer_id: int,
) -> list[str]:
    """
    Скачать вложения по URL и загрузить заново через VK Upload API.

    Возвращает список attachment-строк (например, ["photo-123_456", "doc-123_789"]),
    готовых для использования в messages.send(attachment=...).

    Args:
        api: VK API instance
        attachment_urls: Результат get_attachment_urls()
        peer_id: ID диалога, куда будут отправлены вложения
    """
    result = []
    photo_uploader = PhotoMessageUploader(api)
    doc_uploader = DocMessagesUploader(api)

    async with aiohttp.ClientSession() as session:
        for att in attachment_urls:
            try:
                async with session.get(att["url"]) as resp:
                    if resp.status != 200:
                        logger.warning(f"Failed to download attachment: HTTP {resp.status}")
                        continue
                    data = await resp.read()

                if not data:
                    logger.warning(f"Empty data for attachment: {att['url'][:80]}")
                    continue

                if att["type"] == "photo":
                    # Передаём raw bytes — uploader сам обернёт в BytesIO и выставит .name
                    attachment_str = await photo_uploader.upload(
                        data, peer_id=peer_id
                    )
                else:
                    # title передаётся как kwarg — DocUploader.raw_upload() извлекает его из params
                    attachment_str = await doc_uploader.upload(
                        file_source=data,
                        peer_id=peer_id,
                        title=att["title"],
                    )
                result.append(attachment_str)
            except Exception as e:
                logger.warning(f"Failed to reupload attachment ({att['type']}): {e}")

    return result
