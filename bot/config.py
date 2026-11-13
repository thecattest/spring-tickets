"""
Configuration management for the VK bot.

Loads settings from environment variables and provides centralized configuration.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file
load_dotenv()

# VK Bot Configuration
VK_BOT_TOKEN = os.getenv("VK_BOT_TOKEN", "")
VK_GROUP_ID = int(os.getenv("VK_GROUP_ID", "0"))

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///tickets.db")

# Владельцы проекта (технический ответственный): управление пользователями
# и технические уведомления (бэкапы, алерты). Список VK ID через запятую.
# Это настройка, а не роль в БД — логические админы сюда не входят.
OWNER_VK_IDS = [
    int(part) for part in os.getenv("OWNER_VK_IDS", "").replace(" ", "").split(",") if part
]


def is_owner(vk_user_id: int) -> bool:
    """Является ли VK-пользователь владельцем проекта."""
    return vk_user_id in OWNER_VK_IDS


# Business Logic Configuration
SEAT_PRICE = int(os.getenv("SEAT_PRICE", "1500"))
DEBTORS_REMINDER_MIN_DAYS = int(os.getenv("DEBTORS_REMINDER_MIN_DAYS", "7"))


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
LAYOUT_FILE = PROJECT_ROOT / "layout.json"



def validate_config():
    """
    Validate required configuration is present.

    Raises:
        ValueError: If required configuration is missing
    """
    errors = []

    if not VK_BOT_TOKEN:
        errors.append("VK_BOT_TOKEN is required")

    if not VK_GROUP_ID:
        errors.append("VK_GROUP_ID is required")

    if not OWNER_VK_IDS:
        errors.append("OWNER_VK_IDS is required (comma-separated VK IDs)")

    if not LAYOUT_FILE.exists():
        errors.append(f"Layout file not found: {LAYOUT_FILE}")

    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))


if __name__ == "__main__":
    # Test configuration
    from logging_config import setup_logging

    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Configuration loaded:")
    logger.info(f"  VK_BOT_TOKEN: {'*' * len(VK_BOT_TOKEN) if VK_BOT_TOKEN else 'NOT SET'}")
    logger.info(f"  VK_GROUP_ID: {VK_GROUP_ID}")
    logger.info(f"  OWNER_VK_IDS: {OWNER_VK_IDS}")
    logger.info(f"  REDIS_HOST: {REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
    logger.info(f"  DATABASE_URL: {DATABASE_URL}")
    logger.info(f"  SEAT_PRICE: {SEAT_PRICE}")
    logger.info(f"  LAYOUT_FILE: {LAYOUT_FILE}")

    try:
        validate_config()
        logger.info("Configuration validation passed!")
    except ValueError as e:
        logger.error(f"Configuration validation failed:\n{e}")
