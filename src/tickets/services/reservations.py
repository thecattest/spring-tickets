"""
Брони: одна активная бронь на покупателя (индекс reservations_one_active_per_buyer).

Всё, что меняет бронь (места, оплата, отмена), сначала берёт её под
блокировку (lock_active: SELECT … FOR UPDATE) и проверяет, что она активна:
параллельные изменения одной брони выполняются по очереди, а в отменённую
бронь ничего не добавить.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tickets.models.base import ReservationState, SeatStatus
from tickets.models.reservation import Reservation
from tickets.models.seat_assignment import SeatAssignment
from tickets.services import audit, seats
from tickets.services.errors import NotAllowedError, ReservationNotActiveError
from tickets.time import utcnow

logger = logging.getLogger(__name__)


async def get(session: AsyncSession, reservation_id: int) -> Reservation | None:
    """Бронь по id в любом состоянии."""
    return await session.get(Reservation, reservation_id)


async def is_active(session: AsyncSession, reservation_id: int) -> bool:
    reservation = await get(session, reservation_id)
    return reservation is not None and reservation.state == ReservationState.ACTIVE


async def get_active(session: AsyncSession, buyer_vk_user_id: int) -> Reservation | None:
    """Активная бронь покупателя (buyer_vk_user_id — VkUser.id, не VK ID)."""
    stmt = select(Reservation).where(
        Reservation.buyer_vk_user_id == buyer_vk_user_id,
        Reservation.state == ReservationState.ACTIVE,
    )
    return await session.scalar(stmt)


async def lock_active(session: AsyncSession, reservation_id: int) -> Reservation:
    """
    Бронь под блокировкой строки до конца транзакции; не активна (или нет) —
    ReservationNotActiveError.
    """
    reservation = await session.scalar(
        select(Reservation).where(Reservation.id == reservation_id).with_for_update()
    )
    if reservation is None or reservation.state != ReservationState.ACTIVE:
        raise ReservationNotActiveError(reservation_id)
    return reservation


async def create(session: AsyncSession, buyer_vk_user_id: int, sold_by_user_id: int) -> Reservation:
    reservation = Reservation(
        buyer_vk_user_id=buyer_vk_user_id,
        sold_by_user_id=sold_by_user_id,
        state=ReservationState.ACTIVE,
    )
    session.add(reservation)
    await session.flush()  # нужен id для аудита
    audit.log(
        session,
        audit.AuditAction.RESERVATION_CREATED,
        entity_type="reservation",
        entity_id=reservation.id,
        actor_user_id=sold_by_user_id,
        payload={"buyer_vk_user_id": buyer_vk_user_id, "sold_by_user_id": sold_by_user_id},
    )
    logger.info("Created reservation %s for VK user %s", reservation.id, buyer_vk_user_id)
    return reservation


async def add_seats(
    session: AsyncSession, reservation_id: int, row: int, seat_list: list[int], user_id: int
) -> list[SeatAssignment]:
    """Добавить места в активную бронь: все или ни одного (SeatOccupiedError)."""
    reservation = await lock_active(session, reservation_id)
    assignments = await seats.occupy(
        session,
        row,
        seat_list,
        status=SeatStatus.BOOKED,
        created_by_user_id=user_id,
        reservation_id=reservation_id,
    )
    reservation.last_activity_at = utcnow()
    audit.log(
        session,
        audit.AuditAction.SEATS_ADDED,
        entity_type="reservation",
        entity_id=reservation_id,
        actor_user_id=user_id,
        payload={"row": row, "seats": seat_list, "count": len(seat_list)},
    )
    logger.info("Added %d seats to reservation %s: row %s", len(seat_list), reservation_id, row)
    return assignments


async def remove_seats(
    session: AsyncSession, reservation_id: int, row: int, seat_list: list[int], user_id: int
) -> int:
    """Убрать неоплаченные места из активной брони; возвращает их число."""
    reservation = await lock_active(session, reservation_id)
    assignments = await seats.booked_of_reservation(session, reservation_id, row, seat_list)
    seats.release(session, assignments, user_id)
    reservation.last_activity_at = utcnow()
    audit.log(
        session,
        audit.AuditAction.SEATS_REMOVED,
        entity_type="reservation",
        entity_id=reservation_id,
        actor_user_id=user_id,
        payload={"row": row, "seats": seat_list, "count": len(seat_list)},
    )
    logger.info("Released %d seats from reservation %s", len(assignments), reservation_id)
    return len(assignments)


async def cancel(session: AsyncSession, reservation_id: int, user_id: int, is_admin: bool) -> None:
    """Отменить бронь и освободить места; с оплаченными местами — только админ."""
    reservation = await lock_active(session, reservation_id)
    active = await seats.of_reservation(session, reservation_id)
    paid = [s for s in active if s.status == SeatStatus.PAID]
    if paid and not is_admin:
        raise NotAllowedError(
            f"Cannot cancel reservation with {len(paid)} PAID seats. Admin permission required."
        )
    seats.release(session, active, user_id)
    reservation.state = ReservationState.CANCELLED
    reservation.last_activity_at = utcnow()
    audit.log(
        session,
        audit.AuditAction.RESERVATION_CANCELLED,
        entity_type="reservation",
        entity_id=reservation_id,
        actor_user_id=user_id,
        payload={"total_seats": len(active), "paid_seats": len(paid), "is_admin": is_admin},
    )
    logger.info("Cancelled reservation %s: %d seats released", reservation_id, len(active))
