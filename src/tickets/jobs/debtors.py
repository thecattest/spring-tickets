"""
Напоминания о должниках: python -m tickets.jobs.debtors (cron, раз в 3 дня в 20:00).

Каждый активный билетёр получает в VK список только своих покупателей,
у которых есть неоплаченные места и не было активности
DEBTORS_REMINDER_MIN_DAYS+ дней. Билетёры без должников пропускаются.

Ошибка отправки одному билетёру не мешает остальным; если ошибки были,
задача в конце падает — владелец получит уведомление (jobs.runner).
"""

import logging
import random

from vkbottle import API

from tickets.config import app_settings, vk_settings
from tickets.db import unit_of_work
from tickets.formatting import pluralize_seats
from tickets.jobs.runner import run_job
from tickets.models.user import AppUser
from tickets.services import reports, users

logger = logging.getLogger("jobs.debtors")


# Короткие транзакции; отправка в VK — между ними, не внутри (docs/architecture.md → Транзакции)
async def get_all_active_sellers() -> list[AppUser]:
    async with unit_of_work() as session:
        return await users.active_sellers(session)


async def get_debtors(seller_id: int, min_days: int) -> list[dict]:
    async with unit_of_work() as session:
        return await reports.debtors(session, seller_id=seller_id, min_days=min_days)


async def log_reminder_sent(seller_id: int, debtor_count: int) -> None:
    async with unit_of_work() as session:
        await reports.log_reminder_sent(session, seller_id, debtor_count)


def format_reminder(debtors: list) -> str:
    """
    Format compact debtor list for VK reminder messages sent to sellers.

    Args:
        debtors: List of debtor dicts from reports.debtors()
                 Each dict has: buyer_display_name, buyer_vk_id,
                 booked_seat_count, debt_amount, days_since_activity

    Returns:
        Formatted multi-line string with header and compact per-debtor entries
    """
    count = len(debtors)
    lines = [f"Напоминание о должниках ({count}):", ""]

    for debtor in debtors:
        vk_id = debtor.get("buyer_vk_id")
        name = debtor["buyer_display_name"]
        header = f"{name} (vk.com/id{vk_id})" if vk_id else name
        lines.append(
            f"{header} -- "
            f"{debtor['booked_seat_count']} {pluralize_seats(debtor['booked_seat_count'])}, "
            f"{debtor['debt_amount']} руб., "
            f"{debtor['days_since_activity']} дн. без активности"
        )

    return "\n".join(lines)


async def send_reminders() -> None:
    token = vk_settings().vk_bot_token.get_secret_value()
    min_days = app_settings().debtors_reminder_min_days

    sellers = await get_all_active_sellers()
    logger.info("Processing %d active sellers", len(sellers))

    sent, skipped, failed = 0, 0, []
    api = API(token)
    try:
        for seller in sellers:
            debtors = await get_debtors(seller_id=seller.id, min_days=min_days)
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
            await log_reminder_sent(seller_id=seller.id, debtor_count=len(debtors))
    finally:
        await api.http_client.close()

    logger.info("Sent: %d, skipped (no debtors): %d, failed: %d", sent, skipped, len(failed))
    if failed:
        raise RuntimeError(f"Reminders not sent to sellers {failed} (sent to {sent})")


def main() -> None:
    run_job("debtors", send_reminders())


if __name__ == "__main__":
    main()
