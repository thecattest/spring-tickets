"""Оплаты: частичная оплата N из M мест брони."""

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tickets.config import app_settings
from tickets.models.base import ActorType, SeatStatus
from tickets.models.payment import Payment, PaymentSeat
from tickets.models.reservation import Reservation
from tickets.models.seat_assignment import SeatAssignment
from tickets.models.user import AppUser
from tickets.models.vk_user import VkUser
from tickets.services import audit, reservations, seats
from tickets.services.errors import InsufficientSeatsError
from tickets.time import utcnow

logger = logging.getLogger(__name__)


async def record(
    session: AsyncSession,
    reservation_id: int,
    seat_count: int,
    user_id: int,
    *,
    vk_message_url: str | None = None,
    vk_message_ts: datetime | None = None,
    receipt_attachments: str | None = None,
) -> tuple[Payment, list[SeatAssignment]]:
    """
    Оплатить seat_count мест брони: первые неоплаченные по порядку (ряд, место).

    Бронь берётся под блокировку (FOR UPDATE) до конца транзакции: вторая
    оплата той же брони ждёт первую и видит уже оплаченные места — две оплаты
    не выберут одни и те же места.
    """
    reservation = await reservations.lock_active(session, reservation_id)
    booked = [
        s
        for s in await seats.of_reservation(session, reservation_id)
        if s.status == SeatStatus.BOOKED
    ]
    if len(booked) < seat_count:
        raise InsufficientSeatsError(seat_count, len(booked))
    selected, remaining = booked[:seat_count], booked[seat_count:]

    amount = Decimal(seat_count) * Decimal(app_settings().seat_price)
    payment = Payment(
        reservation_id=reservation_id,
        recorded_by_user_id=user_id,
        vk_message_url=vk_message_url,
        vk_message_ts=vk_message_ts,
        payment_amount=amount,
        seat_count=seat_count,
        receipt_attachments=receipt_attachments,
    )
    session.add(payment)
    await session.flush()  # нужен payment.id для PaymentSeat и аудита
    for seat in selected:
        seat.status = SeatStatus.PAID
        session.add(PaymentSeat(payment_id=payment.id, seat_assignment_id=seat.id))
    reservation.last_activity_at = utcnow()

    audit.log(
        session,
        audit.AuditAction.PAYMENT_RECORDED,
        entity_type="payment",
        entity_id=payment.id,
        actor_user_id=user_id,
        payload={
            "reservation_id": reservation_id,
            "seat_count": seat_count,
            "payment_amount": float(amount),
            "seat_ids": [s.id for s in selected],
            "partial": bool(remaining),
        },
    )
    logger.info(
        "Recorded payment %s for reservation %s: %d seats", payment.id, reservation_id, seat_count
    )
    return payment, selected


# --- страница оплат (веб) ---------------------------------------------------


def _active_seat_count():
    """Сколько мест оплаты ещё не освобождено (оплата отменённой брони не в счёт)."""
    return (
        select(func.count(PaymentSeat.payment_id))
        .join(SeatAssignment, PaymentSeat.seat_assignment_id == SeatAssignment.id)
        .where(PaymentSeat.payment_id == Payment.id, SeatAssignment.released_at.is_(None))
        .correlate(Payment)
        .scalar_subquery()
    )


async def page(session: AsyncSession) -> dict:
    """
    Данные страницы оплат: оплаты с покупателем и билетёром (новые первыми),
    места по статусам, сумма оплат и число неоплаченных мест.
    """
    active = _active_seat_count()
    rows = await session.execute(
        select(Payment, VkUser.display_name, VkUser.vk_user_id, AppUser.display_name)
        .join(Reservation, Payment.reservation_id == Reservation.id)
        .join(VkUser, Reservation.buyer_vk_user_id == VkUser.id)
        .join(AppUser, Payment.recorded_by_user_id == AppUser.id)
        .where(active > 0)
        .order_by(Payment.recorded_at.desc())
    )
    by_status = dict(
        (
            await session.execute(
                select(SeatAssignment.status, func.count())
                .where(SeatAssignment.released_at.is_(None))
                .group_by(SeatAssignment.status)
            )
        ).all()
    )
    total_paid = await session.scalar(
        select(func.coalesce(func.sum(Payment.payment_amount), 0)).where(active > 0)
    )
    return {
        "payments": [
            {"payment": p, "buyer_name": buyer, "buyer_vk_id": buyer_vk_id, "seller_name": seller}
            for p, buyer, buyer_vk_id, seller in rows
        ],
        "seats_by_status": {status.value: n for status, n in by_status.items()},
        "total_paid": Decimal(total_paid or 0),
    }


async def verify_all(session: AsyncSession, *, ip: str | None) -> list[int]:
    """
    Отметить все непроверенные оплаты проверенными («Проверено» на странице
    оплат); одна запись аудита со списком id. Возвращает отмеченные id.
    """
    ids = list(
        await session.scalars(
            update(Payment)
            .where(Payment.is_verified.is_(False))
            .values(is_verified=True)
            .returning(Payment.id)
        )
    )
    if ids:
        audit.log(
            session,
            audit.AuditAction.PAYMENTS_VERIFIED,
            entity_type="payment",
            actor_user_id=None,
            actor_type=ActorType.WEB_ADMIN,
            payload={"payment_ids": sorted(ids), "ip": ip},
        )
    logger.info("Verified %d payments (ip=%s)", len(ids), ip)
    return ids
