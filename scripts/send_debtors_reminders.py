#!/usr/bin/env python3
"""
Standalone cron script for sending debtor reminders to sellers via VK.

Each active seller receives a VK message listing only their own clients with
overdue unpaid bookings (7+ days of no activity with BOOKED seats).

Sellers without debtors are silently skipped.
One VK API failure does not abort the remaining sellers.

Crontab entry (every 3 days at 20:00 Moscow time):
  TZ=Europe/Moscow
  0 20 */3 * * /path/to/venv/bin/python /path/to/project/scripts/send_debtors_reminders.py >> /var/log/debtors_reminders.log 2>&1
"""

import asyncio
import logging
import sys
from pathlib import Path

# Make project root importable regardless of working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from vkbottle.bot import Bot
from vkbottle import VKAPIError

from bot.config import VK_BOT_TOKEN
from bot.utils.db import get_debtors, get_all_active_sellers, log_reminder_sent
from bot.messages import format_reminder
from database import init_db


async def main() -> None:
    """
    Main entry point for the debtor reminder cron job.

    Workflow:
    1. Ensure DB tables exist
    2. Create VKBottle Bot instance
    3. Fetch all active sellers (those with vk_user_id set)
    4. For each seller:
        a. Fetch their debtors (sold_by_user_id = seller.id)
        b. Skip if no debtors
        c. Format and send VK message
        d. Log audit entry on success
        e. Log error and continue on VK API or other failure
    5. Print summary: sent / skipped / error counts
    """
    init_db()

    bot = Bot(token=VK_BOT_TOKEN)

    sellers = get_all_active_sellers()
    logger.info(f"Processing {len(sellers)} active sellers")

    sent_count = 0
    skipped_count = 0
    error_count = 0

    for seller in sellers:
        debtors = get_debtors(seller_id=seller.id)

        if not debtors:
            skipped_count += 1
            logger.debug(f"Seller {seller.id} (vk_user_id={seller.vk_user_id}): no debtors, skipping")
            continue

        message_text = format_reminder(debtors)

        try:
            await bot.api.messages.send(
                peer_id=seller.vk_user_id,
                message=message_text,
                random_id=0,
            )
            sent_count += 1
            logger.info(
                f"Sent reminder to seller {seller.id} (vk_user_id={seller.vk_user_id}): "
                f"{len(debtors)} debtors"
            )
            log_reminder_sent(seller_id=seller.id, debtor_count=len(debtors))

        except VKAPIError as e:
            error_count += 1
            logger.error(
                f"VK API error sending to seller {seller.id} "
                f"(vk_user_id={seller.vk_user_id}): {e}"
            )
            # Continue processing remaining sellers

        except Exception as e:
            error_count += 1
            logger.error(
                f"Unexpected error sending to seller {seller.id} "
                f"(vk_user_id={seller.vk_user_id}): {e}"
            )
            # Continue processing remaining sellers

    logger.info(
        f"Done. Sent: {sent_count}, Skipped: {skipped_count}, Errors: {error_count}"
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )
    logger = logging.getLogger(__name__)
    asyncio.run(main())
else:
    logger = logging.getLogger(__name__)
