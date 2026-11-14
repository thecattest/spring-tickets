"""
Константы бота, не зависящие от окружения.

Настройки (токены, Redis, владельцы, цены) — в config.py в корне проекта
(pydantic-settings): vk_settings(), redis_settings(), app_settings().
"""

from config import PROJECT_ROOT

# Геометрия зала — данные предметной области, а не конфиг
LAYOUT_FILE = PROJECT_ROOT / "layout.json"
