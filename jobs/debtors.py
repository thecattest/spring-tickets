"""
Напоминания о должниках: python -m jobs.debtors (cron, раз в 3 дня в 20:00).

Каждый активный билетёр получает в VK список только своих покупателей,
у которых есть неоплаченные места и не было активности
DEBTORS_REMINDER_MIN_DAYS+ дней. Билетёры без должников пропускаются.

Ошибка отправки одному билетёру не мешает остальным; если ошибки были,
задача в конце падает — владелец получит уведомление (jobs.runner).
"""

import logging
import random

from vkbottle import API

from bot.config import DEBTORS_REMINDER_MIN_DAYS, VK_BOT_TOKEN
from bot.messages import format_reminder
from bot.utils.db import get_all_active_sellers, get_debtors, log_reminder_sent
from jobs.runner import run_job

logger = logging.getLogger("jobs.debtors")


async def send_reminders() -> None:
    if not VK_BOT_TOKEN:
        raise RuntimeError("VK_BOT_TOKEN is not set")

    sellers = get_all_active_sellers()
    logger.info("Processing %d active sellers", len(sellers))

    sent, skipped, failed = 0, 0, []
    api = API(VK_BOT_TOKEN)
    try:
        for seller in sellers:
            debtors = get_debtors(seller_id=seller.id, min_days=DEBTORS_REMINDER_MIN_DAYS)
            if not debtors:
                skipped += 1
                continue

            try:
                await api.messages.send(
                    peer_id=seller.vk_user_id,
                    message=format_reminder(debtors),
                    # VK отбрасывает повтор с тем же random_id (ретрай запроса)
                    random_id=random.getrandbits(31),
                )
            except Exception:
                logger.exception("Failed to send reminder to seller %s", seller.id)
                failed.append(seller.id)
                continue

            sent += 1
            logger.info("Reminder sent to seller %s: %d debtors", seller.id, len(debtors))
            log_reminder_sent(seller_id=seller.id, debtor_count=len(debtors))
    finally:
        await api.http_client.close()

    logger.info("Sent: %d, skipped (no debtors): %d, failed: %d", sent, skipped, len(failed))
    if failed:
        raise RuntimeError(f"Reminders not sent to sellers {failed} (sent to {sent})")


def main() -> None:
    run_job("debtors", send_reminders())


if __name__ == "__main__":
    main()
