#!/usr/bin/env python3
"""
Standalone cron script for backing up the SQLite database.

1. Copies the DB file to ~/tickets-backup/ with timestamp name (dd.MM-HH.mm.db)
2. Sends the backup file to every project owner (OWNER_VK_IDS) via bot message

Crontab entry (every hour):
  0 * * * * /path/to/venv/bin/python /path/to/project/scripts/backup_db.py >> /path/to/logs/backup.log 2>&1
"""

import asyncio
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Make project root importable regardless of working directory
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import os
from vkbottle.bot import Bot

from bot.config import OWNER_VK_IDS
from database import SQLITE_PATH

from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

VK_BOT_TOKEN = os.getenv("VK_BOT_TOKEN", "")
DB_PATH = SQLITE_PATH  # из DATABASE_URL, относительные пути — от корня проекта
BACKUP_DIR = Path.home() / "tickets-backup"


async def main():
    if not VK_BOT_TOKEN:
        logger.error("VK_BOT_TOKEN not set")
        sys.exit(1)

    if DB_PATH is None:
        logger.error("DATABASE_URL is not a file-based SQLite database, nothing to back up")
        sys.exit(1)

    if not DB_PATH.exists():
        logger.error(f"Database not found: {DB_PATH}")
        sys.exit(1)

    # Create backup directory
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Copy DB with timestamp name
    now = datetime.now()
    backup_name = now.strftime("%d.%m-%H.%M") + ".db"
    backup_path = BACKUP_DIR / backup_name
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(backup_path)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    logger.info(f"Backup created: {backup_path}")

    if not OWNER_VK_IDS:
        logger.warning("OWNER_VK_IDS not set, backup is not sent")
        return

    # Send via VK bot to every owner (document upload is per recipient)
    bot = Bot(token=VK_BOT_TOKEN)
    try:
        for owner_vk_id in OWNER_VK_IDS:
            try:
                await _send_backup(bot, owner_vk_id, backup_path, backup_name)
                logger.info(f"Backup sent to VK user {owner_vk_id}")
            except Exception as e:
                logger.error(f"Failed to send backup to VK user {owner_vk_id}: {e}")
    finally:
        await bot.api.http_client.close()


async def _send_backup(bot: Bot, peer_id: int, backup_path: Path, backup_name: str) -> None:
    import aiohttp

    upload_server = await bot.api.docs.get_messages_upload_server(type="doc", peer_id=peer_id)

    async with aiohttp.ClientSession() as session:
        with open(backup_path, "rb") as f:
            form = aiohttp.FormData()
            form.add_field("file", f, filename=backup_name)
            async with session.post(upload_server.upload_url, data=form) as resp:
                upload_result = await resp.json()

    if "file" not in upload_result:
        raise RuntimeError(f"Upload failed: {upload_result}")

    saved = await bot.api.docs.save(file=upload_result["file"], title=backup_name)
    doc = saved.doc
    await bot.api.messages.send(
        peer_id=peer_id,
        message=f"Бэкап БД: {backup_name}",
        attachment=f"doc{doc.owner_id}_{doc.id}",
        random_id=0,
    )


if __name__ == "__main__":
    asyncio.run(main())
