#!/usr/bin/env python3
"""
Standalone cron script for backing up the PostgreSQL database.

1. pg_dump (custom format, compressed) to ~/tickets-backup/<dd.MM-HH.mm>.dump
   Restore: pg_restore --clean --if-exists -d <url> <file>
   pg_dump must be the same major version as the server or newer.
   Rotation and the Docker job — ROADMAP stage 4.
2. Sends the backup file to every project owner (OWNER_VK_IDS) via bot message

Crontab entry (every hour):
  0 * * * * /path/to/venv/bin/python /path/to/project/scripts/backup_db.py >> /path/to/logs/backup.log 2>&1
"""

import asyncio
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Make project root importable regardless of working directory
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

import os

from sqlalchemy.engine import make_url
from vkbottle.bot import Bot

from bot.config import OWNER_VK_IDS
from database import DATABASE_URL
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

VK_BOT_TOKEN = os.getenv("VK_BOT_TOKEN", "")
BACKUP_DIR = Path.home() / "tickets-backup"


async def main():
    if not VK_BOT_TOKEN:
        logger.error("VK_BOT_TOKEN not set")
        sys.exit(1)

    # Create backup directory
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Copy DB with timestamp name
    now = datetime.now()
    backup_name = now.strftime("%d.%m-%H.%M") + ".dump"
    backup_path = BACKUP_DIR / backup_name
    # pg_dump понимает libpq-URL без указания драйвера SQLAlchemy (+psycopg)
    libpq_url = (
        make_url(DATABASE_URL).set(drivername="postgresql").render_as_string(hide_password=False)
    )
    result = subprocess.run(
        ["pg_dump", "--format=custom", f"--file={backup_path}", f"--dbname={libpq_url}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error(f"pg_dump failed: {result.stderr.strip()}")
        sys.exit(1)
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
