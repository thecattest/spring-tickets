"""Отчёты и выборки для чтения: должники и напоминания о них."""

import logging
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tickets.config import app_settings
from tickets.models.base import ActorType, ReservationState, SeatStatus
from tickets.models.reservation import Reservation
from tickets.models.seat_assignment import SeatAssignment
from tickets.models.vk_user import VkUser
from tickets.services import audit
from tickets.time import utcnow

logger = logging.getLogger(__name__)


async def debtors(
    session: AsyncSession, seller_id: int | None = None, min_days: int = 0
) -> list[dict]:
    """
    Активные брони с неоплаченными местами, давние первыми.

    seller_id — только брони этого билетёра (AppUser.id), None — все.
    min_days > 0 — без активности не меньше min_days дней.
    """
    booked_count = (
        select(func.count(SeatAssignment.id))
        .where(
            SeatAssignment.reservation_id == Reservation.id,
            SeatAssignment.released_at.is_(None),
            SeatAssignment.status == SeatStatus.BOOKED,
        )
        .scalar_subquery()
    )
    stmt = (
        select(Reservation, VkUser, booked_count.label("booked_count"))
        .join(VkUser, Reservation.buyer_vk_user_id == VkUser.id)
        .where(Reservation.state == ReservationState.ACTIVE, booked_count > 0)
        .order_by(Reservation.last_activity_at.asc())
    )
    if min_days > 0:
        stmt = stmt.where(Reservation.last_activity_at <= utcnow() - timedelta(days=min_days))
    if seller_id is not None:
        stmt = stmt.where(Reservation.sold_by_user_id == seller_id)

    now = utcnow()
    price = Decimal(app_settings().seat_price)
    result = [
        {
            "reservation_id": reservation.id,
            "buyer_display_name": vk_user.display_name,
            "buyer_vk_id": vk_user.vk_user_id,
            "booked_seat_count": count,
            "debt_amount": Decimal(count) * price,
            "days_since_activity": (now - reservation.last_activity_at).days,
            "last_activity_at": reservation.last_activity_at,
        }
        for reservation, vk_user, count in await session.execute(stmt)
    ]
    logger.info("debtors(seller_id=%s): found %d", seller_id, len(result))
    return result


async def log_reminder_sent(session: AsyncSession, seller_id: int, debtor_count: int) -> None:
    """Аудит: напоминание о должниках отправлено (после отправки, отдельной транзакцией)."""
    audit.log(
        session,
        audit.AuditAction.DEBTORS_NOTIFICATION_SENT,
        entity_type=audit.AuditEntity.REMINDER,
        actor_user_id=seller_id,
        actor_type=ActorType.SYSTEM,
        payload={"seller_id": seller_id, "debtor_count": debtor_count},
    )


# --- страницы веба ----------------------------------------------------------


async def occupied_seats(session: AsyncSession) -> set[tuple[int, int]]:
    """Занятые места зала (ряд, место) — для публичной схемы."""
    rows = await session.execute(
        select(SeatAssignment.row_number, SeatAssignment.seat_number).where(
            SeatAssignment.released_at.is_(None)
        )
    )
    return {(row, seat) for row, seat in rows}


async def concert_day(session: AsyncSession) -> tuple[list[dict], list[dict]]:
    """
    Для «дня концерта»: места броней (с покупателем) и места резервов.

    Брони: [{'reservation_id', 'buyer_name', 'buyer_profile_url', 'row', 'seat', 'status'}].
    Резервы: [{'row', 'seat', 'note'}].
    """
    bookings = await session.execute(
        select(
            SeatAssignment.row_number,
            SeatAssignment.seat_number,
            SeatAssignment.status,
            Reservation.id,
            VkUser.display_name,
            VkUser.profile_url,
        )
        .join(Reservation, SeatAssignment.reservation_id == Reservation.id)
        .join(VkUser, Reservation.buyer_vk_user_id == VkUser.id)
        .where(
            SeatAssignment.released_at.is_(None),
            SeatAssignment.status.in_([SeatStatus.BOOKED, SeatStatus.PAID]),
        )
    )
    reserves = await session.execute(
        select(SeatAssignment.row_number, SeatAssignment.seat_number, SeatAssignment.note).where(
            SeatAssignment.released_at.is_(None), SeatAssignment.status == SeatStatus.RESERVED
        )
    )
    return (
        [
            {
                "reservation_id": rid,
                "buyer_name": name,
                "buyer_profile_url": url,
                "row": row,
                "seat": seat,
                "status": status,
            }
            for row, seat, status, rid, name, url in bookings
        ],
        [{"row": row, "seat": seat, "note": note} for row, seat, note in reserves],
    )
