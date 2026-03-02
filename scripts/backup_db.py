#!/usr/bin/env python3
"""
Standalone cron script for backing up the SQLite database.

1. Copies the DB file to ~/tickets-backup/ with timestamp name (dd.MM-HH.mm.db)
2. Sends the backup file to a VK user via bot message

Crontab entry (every hour):
  0 * * * * /path/to/venv/bin/python /path/to/project/scripts/backup_db.py >> /path/to/logs/backup.log 2>&1
"""

import asyncio
import logging
import shutil
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

VK_BOT_TOKEN = os.getenv("VK_BOT_TOKEN", "")
RECIPIENT_VK_ID = 498417215
DB_PATH = PROJECT_ROOT / "tickets.db"
BACKUP_DIR = Path.home() / "tickets-backup"


async def main():
    if not VK_BOT_TOKEN:
        logger.error("VK_BOT_TOKEN not set")
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
    shutil.copy2(DB_PATH, backup_path)
    logger.info(f"Backup created: {backup_path}")

    # Send via VK bot
    bot = Bot(token=VK_BOT_TOKEN)
    try:
        # Upload document
        upload_server = await bot.api.docs.get_messages_upload_server(
            type="doc", peer_id=RECIPIENT_VK_ID,
        )
        upload_url = upload_server.upload_url

        import aiohttp
        async with aiohttp.ClientSession() as session:
            with open(backup_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("file", f, filename=backup_name)
                async with session.post(upload_url, data=form) as resp:
                    upload_result = await resp.json()

        if "file" not in upload_result:
            logger.error(f"Upload failed: {upload_result}")
            return

        saved = await bot.api.docs.save(file=upload_result["file"], title=backup_name)
        doc = saved.doc
        attachment = f"doc{doc.owner_id}_{doc.id}"

        await bot.api.messages.send(
            peer_id=RECIPIENT_VK_ID,
            message=f"Бэкап БД: {backup_name}",
            attachment=attachment,
            random_id=0,
        )
        logger.info(f"Backup sent to VK user {RECIPIENT_VK_ID}")

    except Exception as e:
        logger.error(f"Failed to send backup via VK: {e}")
    finally:
        await bot.api.http_client.close()


if __name__ == "__main__":
    asyncio.run(main())
