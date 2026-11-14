"""
Парсинг ссылок и упоминаний VK из текста сообщения.

Поддерживаемые форматы:
  vk.com/id12345
  vk.com/durov
  https://vk.com/id12345
  https://m.vk.com/id12345
  www.vk.com/durov
  @durov
  @id12345
"""

import re

_VK_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?vk\.com/([a-zA-Z0-9_.]+)",
    re.IGNORECASE,
)

_VK_MENTION_RE = re.compile(
    r"@([a-zA-Z0-9_.]+)",
)


def parse_vk_link(text: str) -> str | None:
    """
    Извлечь идентификатор пользователя VK из текста.

    Поддерживает ссылки (vk.com/...) и упоминания (@screen_name).

    Returns:
        ID или screen_name (например "id12345" или "durov"), или None.
    """
    m = _VK_LINK_RE.search(text)
    if m:
        return m.group(1)
    m = _VK_MENTION_RE.search(text)
    if m:
        return m.group(1)
    return None
