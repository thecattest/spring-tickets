"""
Единая настройка логирования для бота, веба и задач.

Вывод только в stdout (в Docker логи собирает и ротирует сам Docker),
уровень — переменная LOG_LEVEL (по умолчанию INFO), текстовый формат.
Вызывается один раз на старте процесса; других basicConfig в коде нет.
"""

import logging

from tickets.config import app_settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Сторонние библиотеки, которые на INFO слишком многословны
_NOISY_LOGGERS = ("vkbottle", "aiohttp")


def setup_logging() -> None:
    level = app_settings().log_level.upper()
    # Неверный уровень → ValueError на старте, а не тихо INFO
    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=DATE_FORMAT)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
