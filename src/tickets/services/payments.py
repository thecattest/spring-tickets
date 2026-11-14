"""Оплаты: частичная оплата N из M мест брони."""

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from tickets.config import app_settings
from tickets.models.base import SeatStatus
from tickets.models.payment import Payment, PaymentSeat
from tickets.models.seat_assignment import SeatAssignment
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
