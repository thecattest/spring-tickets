"""
Места: занятость зала, места броней и резервы (места под гостей без брони).

Источник правды о занятости — активные (released_at IS NULL) строки
seat_assignments; от двойного занятия защищает частичный уникальный индекс
seat_assignments_one_active_per_seat.
"""

import itertools
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tickets.hall import get_seat_count
from tickets.models.base import SeatStatus
from tickets.models.seat_assignment import SeatAssignment
from tickets.services import audit
from tickets.services.errors import NotFoundError, SeatOccupiedError
from tickets.time import utcnow

logger = logging.getLogger(__name__)


def _active():
    return select(SeatAssignment).where(SeatAssignment.released_at.is_(None))


# --- занятость зала ---------------------------------------------------------


def get_assignment(session: Session, row: int, seat: int) -> SeatAssignment | None:
    """Кто сейчас занимает место (бронь или резерв), None — свободно."""
    stmt = _active().where(SeatAssignment.row_number == row, SeatAssignment.seat_number == seat)
    return session.scalars(stmt).first()


def is_available(session: Session, row: int, seat: int) -> bool:
    return get_assignment(session, row, seat) is None


def available_in_row(session: Session, row: int) -> list[int]:
    """Свободные места ряда по порядку."""
    stmt = select(SeatAssignment.seat_number).where(
        SeatAssignment.row_number == row, SeatAssignment.released_at.is_(None)
    )
    occupied = set(session.scalars(stmt))
    return [s for s in range(1, get_seat_count(row) + 1) if s not in occupied]


def find_conflicts(session: Session, row: int, seats: list[int]) -> list[dict]:
    """Какие из мест уже заняты — в формате SeatOccupiedError.conflicts."""
    stmt = (
        _active()
        .where(SeatAssignment.row_number == row, SeatAssignment.seat_number.in_(seats))
        .order_by(SeatAssignment.seat_number)
    )
    return [
        {
            "row": row,
            "seat": a.seat_number,
            "status": a.status,
            "note": a.note,
            "reservation_id": a.reservation_id,
        }
        for a in session.scalars(stmt)
    ]


def occupy(
    session: Session,
    row: int,
    seats: list[int],
    *,
    status: SeatStatus,
    created_by_user_id: int,
    reservation_id: int | None = None,
    note: str | None = None,
) -> list[SeatAssignment]:
    """
    Занять места: все или ни одного.

    Сначала проверка (понятный список конфликтов), затем вставка в SAVEPOINT.
    Если место заняли параллельно — между проверкой и вставкой, — сработает
    уникальный индекс: откатываем только SAVEPOINT, перечитываем занятые места
    и поднимаем SeatOccupiedError, а не общую ошибку базы.
    """
    conflicts = find_conflicts(session, row, seats)
    if conflicts:
        raise SeatOccupiedError(conflicts)

    assignments = [
        SeatAssignment(
            row_number=row,
            seat_number=seat,
            status=status,
            reservation_id=reservation_id,
            created_by_user_id=created_by_user_id,
            note=note,
        )
        for seat in seats
    ]
    try:
        with session.begin_nested():
            session.add_all(assignments)
            session.flush()
    except IntegrityError:
        raise SeatOccupiedError(find_conflicts(session, row, seats)) from None
    return assignments


def release(session: Session, assignments: list[SeatAssignment], user_id: int) -> None:
    """Освободить места (мягко: released_at, история сохраняется)."""
    now = utcnow()
    for assignment in assignments:
        assignment.released_at = now
        assignment.released_by_user_id = user_id


# --- места брони ------------------------------------------------------------


def of_reservation(session: Session, reservation_id: int) -> list[SeatAssignment]:
    """Активные места брони по порядку (ряд, место)."""
    stmt = (
        _active()
        .where(SeatAssignment.reservation_id == reservation_id)
        .order_by(SeatAssignment.row_number, SeatAssignment.seat_number)
    )
    return list(session.scalars(stmt))


def of_reservation_in_row(session: Session, reservation_id: int, row: int) -> list[int]:
    """Номера мест брони в ряду (любой статус)."""
    stmt = select(SeatAssignment.seat_number).where(
        SeatAssignment.reservation_id == reservation_id,
        SeatAssignment.row_number == row,
        SeatAssignment.released_at.is_(None),
    )
    return list(session.scalars(stmt))


def booked_of_reservation(
    session: Session, reservation_id: int, row: int, seats: list[int]
) -> list[SeatAssignment]:
    """
    Неоплаченные места брони из списка — все, иначе NotFoundError (место не
    из этой брони, уже освобождено или оплачено: оплаченные так не удаляются).
    """
    stmt = _active().where(
        SeatAssignment.reservation_id == reservation_id,
        SeatAssignment.row_number == row,
        SeatAssignment.seat_number.in_(seats),
        SeatAssignment.status == SeatStatus.BOOKED,
    )
    found = list(session.scalars(stmt))
    missing = set(seats) - {a.seat_number for a in found}
    if missing:
        raise NotFoundError(
            f"Cannot release seats: {sorted(missing)} are either not found, "
            "already released, or are PAID"
        )
    return found


# --- резервы (места под гостей, без брони) ----------------------------------


def _reserves():
    return _active().where(
        SeatAssignment.status == SeatStatus.RESERVED, SeatAssignment.reservation_id.is_(None)
    )


def active_reserves(session: Session) -> list[dict]:
    """Резервы, сгруппированные по комментарию и ряду: [{'row', 'seats', 'note'}]."""
    stmt = _reserves().order_by(
        SeatAssignment.note, SeatAssignment.row_number, SeatAssignment.seat_number
    )
    return [
        {"row": row, "seats": sorted(a.seat_number for a in group), "note": note or ""}
        for (note, row), group in itertools.groupby(
            session.scalars(stmt), lambda a: (a.note, a.row_number)
        )
    ]


def reserved_in_row(session: Session, row: int) -> list[int]:
    stmt = select(SeatAssignment.seat_number).where(
        SeatAssignment.row_number == row,
        SeatAssignment.status == SeatStatus.RESERVED,
        SeatAssignment.released_at.is_(None),
        SeatAssignment.reservation_id.is_(None),
    )
    return list(session.scalars(stmt))


def reserve_notes(session: Session, row: int, seats: list[int]) -> dict[int, str | None]:
    """{место: комментарий} для резервов ряда."""
    stmt = select(SeatAssignment.seat_number, SeatAssignment.note).where(
        SeatAssignment.row_number == row,
        SeatAssignment.seat_number.in_(seats),
        SeatAssignment.status == SeatStatus.RESERVED,
        SeatAssignment.released_at.is_(None),
    )
    return {seat: note for seat, note in session.execute(stmt)}


def reserves_in_row(session: Session, row: int, seats: list[int]) -> list[SeatAssignment]:
    """Резервы из списка — все, иначе NotFoundError."""
    stmt = select(SeatAssignment).where(
        SeatAssignment.row_number == row,
        SeatAssignment.seat_number.in_(seats),
        SeatAssignment.status == SeatStatus.RESERVED,
        SeatAssignment.released_at.is_(None),
    )
    found = list(session.scalars(stmt))
    missing = sorted(set(seats) - {a.seat_number for a in found})
    if missing:
        raise NotFoundError(f"Seats not found as active RESERVED in row {row}: {missing}")
    return found


def add_reserve(
    session: Session, row: int, seats: list[int], comment: str, user_id: int
) -> list[SeatAssignment]:
    """Зарезервировать места под гостей (все или ни одного) — с записью аудита."""
    assignments = occupy(
        session, row, seats, status=SeatStatus.RESERVED, created_by_user_id=user_id, note=comment
    )
    audit.log(
        session,
        audit.AuditAction.RESERVE_ADDED,
        entity_type="seat_assignment",
        actor_user_id=user_id,
        payload={
            "row": row,
            "seats": seats,
            "comment": comment,
            "user_id": user_id,
            "count": len(seats),
        },
    )
    logger.info("Added reserve: row %s, seats %s", row, seats)
    return assignments


def release_reserve(session: Session, row: int, seats: list[int], user_id: int) -> list[dict]:
    """Снять резерв; возвращает прежние комментарии [{'seat', 'note'}] — с записью аудита."""
    assignments = reserves_in_row(session, row, seats)
    previous_notes = [{"seat": a.seat_number, "note": a.note} for a in assignments]
    release(session, assignments, user_id)
    audit.log(
        session,
        audit.AuditAction.RESERVE_REMOVED,
        entity_type="seat_assignment",
        actor_user_id=user_id,
        payload={"row": row, "seats": seats, "previous_notes": previous_notes, "user_id": user_id},
    )
    logger.info("Released reserve: row %s, seats %s", row, seats)
    return previous_notes
