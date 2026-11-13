"""
Утилиты для работы с вложениями VK.

Предоставляет функции для извлечения URL вложений из пересланных сообщений
и их повторной загрузки через VK Upload API для отправки в другие диалоги.
"""

import logging

import aiohttp
from vkbottle import ABCAPI

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
        elif att.doc is not None and att.doc.url:
            # Сохраняем ext для корректного content-type при загрузке
            title = att.doc.title or "document"
            if att.doc.ext and "." not in title:
                title = f"{title}.{att.doc.ext}"
            result.append({
                "type": "doc",
                "url": att.doc.url,
                "title": title,
            })
    return result


async def _upload_photo_manual(
    api: ABCAPI,
    data: bytes,
    peer_id: int,
) -> str | None:
    """
    Загрузить фото через VK Upload API вручную.

    vkbottle PhotoMessageUploader не выставляет расширение файла,
    из-за чего VK Upload Server возвращает photo=undefined.

    Returns:
        Attachment string (например "photo-123_456") или None при ошибке.
    """
    try:
        # 1. Получить upload URL
        server_resp = await api.request(
            "photos.getMessagesUploadServer",
            {"peer_id": peer_id},
        )
        upload_url = server_resp["response"]["upload_url"]

        # 2. Загрузить файл — поле "photo", filename с расширением .jpg
        form = aiohttp.FormData()
        form.add_field(
            "photo",
            data,
            filename="photo.jpg",
            content_type="image/jpeg",
        )
        async with (
            aiohttp.ClientSession() as session,
            session.post(upload_url, data=form) as resp,
        ):
            if resp.status != 200:
                logger.warning(f"Photo upload HTTP error: {resp.status}")
                return None
            upload_result = await resp.json()

        if not upload_result or not upload_result.get("photo"):
            logger.warning(f"Photo upload empty response: {upload_result}")
            return None

        # 3. Сохранить фото
        save_resp = await api.request(
            "photos.saveMessagesPhoto",
            {
                "server": upload_result["server"],
                "photo": upload_result["photo"],
                "hash": upload_result["hash"],
            },
        )
        photo = save_resp["response"][0]
        access_key = photo.get("access_key", "")
        ak_suffix = f"_{access_key}" if access_key else ""
        return f"photo{photo['owner_id']}_{photo['id']}{ak_suffix}"

    except Exception as e:
        logger.warning(f"Manual photo upload failed: {e}")
        return None


async def _upload_doc_manual(
    api: ABCAPI,
    data: bytes,
    title: str,
    peer_id: int,
) -> str | None:
    """
    Загрузить документ через VK Upload API вручную (без vkbottle uploader).

    Обходит проблему с пустым ответом от upload-сервера при использовании
    vkbottle DocMessagesUploader с raw bytes.

    Returns:
        Attachment string (например "doc-123_456") или None при ошибке.
    """
    try:
        # 1. Получить upload URL
        server_resp = await api.request(
            "docs.getMessagesUploadServer",
            {"peer_id": peer_id},
        )
        upload_url = server_resp["response"]["upload_url"]

        # 2. Загрузить файл через multipart/form-data
        form = aiohttp.FormData()
        form.add_field(
            "file",
            data,
            filename=title,
            content_type="application/octet-stream",
        )
        async with (
            aiohttp.ClientSession() as session,
            session.post(upload_url, data=form) as resp,
        ):
            if resp.status != 200:
                logger.warning(f"Doc upload HTTP error: {resp.status}")
                return None
            upload_result = await resp.json()

        if not upload_result or not upload_result.get("file"):
            logger.warning(f"Doc upload empty response: {upload_result}")
            return None

        # 3. Сохранить документ
        save_resp = await api.request(
            "docs.save",
            {"file": upload_result["file"], "title": title},
        )
        doc_info = save_resp["response"]
        doc_type = doc_info["type"]
        doc = doc_info[doc_type]
        access_key = doc.get("access_key", "")
        ak_suffix = f"_{access_key}" if access_key else ""
        return f"{doc_type}{doc['owner_id']}_{doc['id']}{ak_suffix}"

    except Exception as e:
        logger.warning(f"Manual doc upload failed: {e}")
        return None


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

                logger.info(f"Downloaded attachment: type={att['type']}, size={len(data)}, title={att.get('title')}")

                if att["type"] == "photo":
                    # Ручной upload фото через VK API (обходит проблему с именем файла)
                    attachment_str = await _upload_photo_manual(
                        api, data, peer_id
                    )
                    if not attachment_str:
                        continue
                else:
                    # Ручной upload документа через VK API (обходит проблему пустого ответа)
                    attachment_str = await _upload_doc_manual(
                        api, data, att["title"], peer_id
                    )
                    if not attachment_str:
                        continue

                result.append(attachment_str)
            except Exception as e:
                logger.warning(f"Failed to reupload attachment ({att['type']}): {e}")

    return result
