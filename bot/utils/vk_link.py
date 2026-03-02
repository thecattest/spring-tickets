"""
Парсинг ссылок на профиль VK из текста сообщения.

Поддерживаемые форматы:
  vk.com/id12345
  vk.com/durov
  https://vk.com/id12345
  https://m.vk.com/id12345
  www.vk.com/durov
"""

import re

_VK_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?vk\.com/([a-zA-Z0-9_.]+)",
    re.IGNORECASE,
)


def parse_vk_link(text: str) -> str | None:
    """
    Извлечь идентификатор пользователя VK из текста.

    Returns:
        ID или screen_name (например "id12345" или "durov"), или None.
    """
    m = _VK_LINK_RE.search(text)
    return m.group(1) if m else None
