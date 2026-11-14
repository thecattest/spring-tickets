"""
Сервисы: транзакции и исправления этапа 6 (ROADMAP) — атомарность, блокировка
при оплате, конфликт мест при гонке, неактивная бронь, аудит в транзакции.
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from tickets.db import unit_of_work
from tickets.models.audit import AuditLog
from tickets.models.base import SeatStatus, UserRole
from tickets.models.payment import Payment
from tickets.models.seat_assignment import SeatAssignment
from tickets.services import audit, payments, reservations, seats, users
from tickets.services.errors import (
    InsufficientSeatsError,
    ReservationNotActiveError,
    SeatOccupiedError,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def seller_id() -> int:
    async with unit_of_work() as s:
        return (await users.add_app_user(s, 201, "Билетёр", UserRole.SELLER)).id


async def new_reservation(seller_id: int, buyer_vk_id: int, row: int, seat_list: list[int]) -> int:
    async with unit_of_work() as s:
        buyer = await users.get_or_create_vk_user(s, buyer_vk_id, f"Покупатель {buyer_vk_id}")
        reservation = await reservations.create(s, buyer.id, seller_id)
        if seat_list:
            await reservations.add_seats(s, reservation.id, row, seat_list, seller_id)
        return reservation.id


async def count(model, *where) -> int:
    async with unit_of_work() as s:
        return await s.scalar(select(func.count()).select_from(model).where(*where))


async def active_seats(status: SeatStatus | None = None) -> int:
    where = [SeatAssignment.released_at.is_(None)]
    if status is not None:
        where.append(SeatAssignment.status == status)
    return await count(SeatAssignment, *where)


# --- атомарность и аудит ----------------------------------------------------


async def test_failure_rolls_back_whole_operation(seller_id, monkeypatch):
    """Упала запись аудита — мест тоже нет: операция целиком или никак."""
    rid = await new_reservation(seller_id, 301, 5, [])

    def broken_log(*args, **kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(audit, "log", broken_log)
    with pytest.raises(RuntimeError):
        async with unit_of_work() as s:
            await reservations.add_seats(s, rid, 5, [1, 2, 3], seller_id)
    assert await active_seats() == 0


async def test_audit_written_with_the_change(seller_id):
    rid = await new_reservation(seller_id, 301, 5, [1, 2])
    added = AuditLog.action_type == audit.AuditAction.SEATS_ADDED.value
    assert await count(AuditLog, added) == 1
    of_reservation = (AuditLog.entity_type == "reservation", AuditLog.entity_id == str(rid))
    assert await count(AuditLog, *of_reservation) == 2  # создание + места


# --- неактивная бронь -------------------------------------------------------


async def test_cancelled_reservation_rejects_changes(seller_id):
    rid = await new_reservation(seller_id, 301, 5, [1, 2])
    async with unit_of_work() as s:
        await reservations.cancel(s, rid, seller_id, is_admin=False)

    for change in (
        lambda s: reservations.add_seats(s, rid, 5, [3], seller_id),
        lambda s: reservations.remove_seats(s, rid, 5, [1], seller_id),
        lambda s: payments.record(s, rid, 1, seller_id),
        lambda s: reservations.cancel(s, rid, seller_id, is_admin=True),
    ):
        with pytest.raises(ReservationNotActiveError):
            async with unit_of_work() as s:
                await change(s)
    assert await active_seats() == 0


# --- конфликт мест ----------------------------------------------------------


async def test_occupied_seat_is_refused(seller_id):
    await new_reservation(seller_id, 301, 5, [3, 4])
    rid2 = await new_reservation(seller_id, 302, 5, [])
    with pytest.raises(SeatOccupiedError) as error:
        async with unit_of_work() as s:
            await reservations.add_seats(s, rid2, 5, [4, 5], seller_id)
    assert [c["seat"] for c in error.value.conflicts] == [4]
    assert await active_seats() == 2  # место 5 тоже не добавлено


async def test_seat_taken_in_parallel_is_seat_occupied_not_db_error(seller_id, monkeypatch):
    """
    Место заняли между проверкой и вставкой: срабатывает уникальный индекс —
    результат SeatOccupiedError с перечитанными конфликтами, а не DatabaseError.
    """
    await new_reservation(seller_id, 301, 5, [4])
    rid2 = await new_reservation(seller_id, 302, 5, [])

    real_find = seats.find_conflicts
    calls = []

    async def stale_check(session, row, seat_list):
        calls.append(row)
        # Первая проверка «не видит» параллельную бронь — как при гонке
        return [] if len(calls) == 1 else await real_find(session, row, seat_list)

    monkeypatch.setattr(seats, "find_conflicts", stale_check)
    with pytest.raises(SeatOccupiedError) as error:
        async with unit_of_work() as s:
            await reservations.add_seats(s, rid2, 5, [4, 5], seller_id)
    assert [c["seat"] for c in error.value.conflicts] == [4]
    assert await active_seats() == 1


# --- гонка при оплате -------------------------------------------------------


async def test_concurrent_payments_of_one_reservation_are_serialized(seller_id):
    """
    Две оплаты одной брони одновременно (две задачи, две транзакции): вторая
    ждёт блокировку первой (FOR UPDATE) и после её коммита видит, что
    оплачивать уже нечего. Ожидание блокировки — await, loop не блокируется.
    """
    rid = await new_reservation(seller_id, 301, 5, [1, 2, 3])
    first_paid, first_may_commit = asyncio.Event(), asyncio.Event()

    async def first():
        async with unit_of_work() as s:
            await payments.record(s, rid, 2, seller_id)
            first_paid.set()
            await first_may_commit.wait()  # транзакция открыта, бронь заблокирована

    async def second():
        await first_paid.wait()
        try:
            async with unit_of_work() as s:
                await payments.record(s, rid, 2, seller_id)
            return "paid"
        except InsufficientSeatsError as e:
            return ("insufficient", e.available)

    first_task = asyncio.create_task(first())
    second_task = asyncio.create_task(second())
    await asyncio.wait_for(first_paid.wait(), 10)
    await asyncio.sleep(0.5)
    assert not second_task.done(), "вторая оплата должна ждать блокировку брони"

    first_may_commit.set()
    await asyncio.wait_for(first_task, 10)
    outcome = await asyncio.wait_for(second_task, 10)

    assert outcome == ("insufficient", 1)  # осталось одно неоплаченное
    assert await count(Payment) == 1
    assert await active_seats(SeatStatus.PAID) == 2
