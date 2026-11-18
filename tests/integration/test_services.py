"""
Сервисы на настоящем Postgres: атомарность и аудит в транзакции, неактивная
бронь, двойное занятие мест (в том числе при гонке), частичная оплата и
блокировка при параллельной оплате, отмена с оплаченными местами, должники.
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from tickets.db import unit_of_work
from tickets.models.audit import AuditLog
from tickets.models.base import SeatStatus, UserRole
from tickets.models.payment import Payment, PaymentSeat
from tickets.models.seat_assignment import SeatAssignment
from tickets.services import audit, payments, reports, reservations, seats, users
from tickets.services.errors import (
    InsufficientSeatsError,
    NotAllowedError,
    NotFoundError,
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


# --- last_activity_at (напоминания о должниках) -----------------------------


async def test_last_activity_counts_changes_not_views(seller_id):
    """
    Активность брони (отсчёт 7 дней до напоминания) — изменения: места,
    оплата, отмена. Просмотр меню брони и напоминания её не сдвигают.
    """
    from datetime import timedelta

    from tickets.models.reservation import Reservation
    from tickets.services import reports
    from tickets.time import utcnow

    rid = await new_reservation(seller_id, 301, 5, [1, 2, 3])
    long_ago = utcnow() - timedelta(days=30)

    async def activity_after(action) -> bool:
        """Сдвинулась ли активность после действия (начинаем с «месяц назад»)."""
        async with unit_of_work() as s:
            (await s.get(Reservation, rid)).last_activity_at = long_ago
        async with unit_of_work() as s:
            await action(s)
        async with unit_of_work() as s:
            return (await s.get(Reservation, rid)).last_activity_at > long_ago

    # Чтение — не активность
    assert not await activity_after(lambda s: seats.of_reservation(s, rid))
    assert not await activity_after(lambda s: reports.log_reminder_sent(s, seller_id, 1))
    # Изменения — активность
    assert await activity_after(lambda s: reservations.add_seats(s, rid, 5, [4], seller_id))
    assert await activity_after(lambda s: reservations.remove_seats(s, rid, 5, [4], seller_id))
    assert await activity_after(lambda s: payments.record(s, rid, 1, seller_id))
    assert await activity_after(lambda s: reservations.cancel(s, rid, seller_id, is_admin=True))


# --- двойное занятие: бронь и резерв ----------------------------------------


async def test_reserve_and_booking_do_not_share_seats(seller_id):
    """Резерв под гостей и бронь занимают места из одного пула."""
    rid = await new_reservation(seller_id, 301, 5, [1])
    async with unit_of_work() as s:
        await seats.add_reserve(s, 5, [2], "Гости", seller_id)

    with pytest.raises(SeatOccupiedError) as error:
        async with unit_of_work() as s:
            await seats.add_reserve(s, 5, [1], "Гости", seller_id)
    assert error.value.conflicts[0]["reservation_id"] == rid

    with pytest.raises(SeatOccupiedError) as error:
        async with unit_of_work() as s:
            await reservations.add_seats(s, rid, 5, [2], seller_id)
    [conflict] = error.value.conflicts
    assert (conflict["status"], conflict["note"]) == (SeatStatus.RESERVED, "Гости")


# --- частичная оплата -------------------------------------------------------


async def test_partial_payment_takes_first_seats_by_row_then_seat(seller_id):
    """Оплата N из M: первые неоплаченные по (ряд, место), сумма N × цена."""
    rid = await new_reservation(seller_id, 301, 5, [3, 1])
    async with unit_of_work() as s:
        await reservations.add_seats(s, rid, 2, [7], seller_id)

    async with unit_of_work() as s:
        payment, paid = await payments.record(s, rid, 2, seller_id)
        assert [(a.row_number, a.seat_number) for a in paid] == [(2, 7), (5, 1)]
        assert (payment.seat_count, payment.payment_amount) == (2, 2 * 1500)

    # Осталось одно неоплаченное: больше оплатить нельзя, ничего не меняется
    with pytest.raises(InsufficientSeatsError) as error:
        async with unit_of_work() as s:
            await payments.record(s, rid, 2, seller_id)
    assert (error.value.requested, error.value.available) == (2, 1)
    assert await count(Payment) == 1

    async with unit_of_work() as s:
        _, paid = await payments.record(s, rid, 1, seller_id)
        assert [(a.row_number, a.seat_number) for a in paid] == [(5, 3)]
    assert await active_seats(SeatStatus.PAID) == 3
    assert await count(PaymentSeat) == 3

    recorded = AuditLog.action_type == audit.AuditAction.PAYMENT_RECORDED.value
    async with unit_of_work() as s:
        flags = [a.payload["partial"] for a in await s.scalars(select(AuditLog).where(recorded))]
    assert sorted(flags) == [False, True]


async def test_paid_seats_cannot_be_removed(seller_id):
    """Убрать из брони можно только неоплаченные места."""
    rid = await new_reservation(seller_id, 301, 5, [1, 2])
    async with unit_of_work() as s:
        await payments.record(s, rid, 1, seller_id)  # оплачено место 1
    with pytest.raises(NotFoundError):
        async with unit_of_work() as s:
            await reservations.remove_seats(s, rid, 5, [1, 2], seller_id)
    assert await active_seats() == 2  # и место 2 осталось: всё или ничего


# --- отмена брони с оплаченными местами -------------------------------------


async def test_seller_cannot_cancel_reservation_with_paid_seats(seller_id):
    rid = await new_reservation(seller_id, 301, 5, [1, 2, 3])
    async with unit_of_work() as s:
        await payments.record(s, rid, 1, seller_id)

    with pytest.raises(NotAllowedError):
        async with unit_of_work() as s:
            await reservations.cancel(s, rid, seller_id, is_admin=False)

    async with unit_of_work() as s:
        assert await reservations.is_active(s, rid)
    assert await active_seats() == 3
    assert await active_seats(SeatStatus.PAID) == 1


async def test_seller_can_cancel_unpaid_reservation(seller_id):
    rid = await new_reservation(seller_id, 301, 5, [1, 2])
    async with unit_of_work() as s:
        await reservations.cancel(s, rid, seller_id, is_admin=False)
    assert await active_seats() == 0


async def test_admin_cancel_releases_paid_seats_and_hides_payment(seller_id):
    """
    Админ отменяет бронь с оплатой: освобождаются все места (и оплаченные),
    оплата пропадает со страницы оплат и из суммы, места снова можно занять.
    """
    rid = await new_reservation(seller_id, 301, 5, [1, 2])
    async with unit_of_work() as s:
        await payments.record(s, rid, 1, seller_id)
    async with unit_of_work() as s:
        assert len((await payments.page(s))["payments"]) == 1

    async with unit_of_work() as s:
        await reservations.cancel(s, rid, seller_id, is_admin=True)

    assert await active_seats() == 0
    async with unit_of_work() as s:
        page = await payments.page(s)
        assert (page["payments"], page["total_paid"], page["seats_by_status"]) == ([], 0, {})
        assert await reports.debtors(s) == []
    cancelled = AuditLog.action_type == audit.AuditAction.RESERVATION_CANCELLED.value
    async with unit_of_work() as s:
        entry = await s.scalar(select(AuditLog).where(cancelled))
        assert entry.payload == {"total_seats": 2, "paid_seats": 1, "is_admin": True}

    # Освободившиеся места — свободны для другой брони
    await new_reservation(seller_id, 302, 5, [1, 2])
    assert await active_seats() == 2


# --- должники ---------------------------------------------------------------


async def test_debtors_are_active_reservations_with_unpaid_seats(seller_id):
    """
    Должник — активная бронь с неоплаченными местами: полностью оплаченная,
    отменённая и пустая брони не в списке. Давние первыми; фильтры по
    билетёру и по числу дней без активности.
    """
    from datetime import timedelta

    from tickets.models.reservation import Reservation
    from tickets.time import utcnow

    async with unit_of_work() as s:
        other_seller = (await users.add_app_user(s, 202, "Второй", UserRole.SELLER)).id

    old = await new_reservation(seller_id, 301, 5, [1, 2])  # 2 неоплаченных
    paid = await new_reservation(seller_id, 302, 5, [3])
    recent = await new_reservation(other_seller, 303, 6, [1, 2])  # 1 из 2 оплачено
    cancelled = await new_reservation(seller_id, 304, 7, [1])
    await new_reservation(seller_id, 305, 5, [])  # пустая
    async with unit_of_work() as s:
        await payments.record(s, paid, 1, seller_id)
        await payments.record(s, recent, 1, other_seller)
        await reservations.cancel(s, cancelled, seller_id, is_admin=False)

    async with unit_of_work() as s:
        (await s.get(Reservation, old)).last_activity_at = utcnow() - timedelta(days=10)
        (await s.get(Reservation, recent)).last_activity_at = utcnow() - timedelta(days=3)

    async with unit_of_work() as s:
        everyone = await reports.debtors(s)
        assert [
            (d["reservation_id"], d["buyer_vk_id"], d["booked_seat_count"], d["debt_amount"])
            for d in everyone
        ] == [(old, 301, 2, 2 * 1500), (recent, 303, 1, 1500)]
        assert [d["days_since_activity"] for d in everyone] == [10, 3]

        assert [d["reservation_id"] for d in await reports.debtors(s, seller_id)] == [old]
        assert [d["reservation_id"] for d in await reports.debtors(s, other_seller)] == [recent]
        assert [d["reservation_id"] for d in await reports.debtors(s, min_days=7)] == [old]


# --- сортировка по-русски (ICU ru-RU, compose: POSTGRES_INITDB_ARGS) ---------


async def test_names_sorted_in_russian_order():
    """
    База создана с ICU ru-RU: кириллица по алфавиту без учёта регистра, «ё»
    рядом с «е». В libc на musl (alpine) было бы по кодам символов:
    «Ёлкин» первым, строчные после всех заглавных.
    """
    names = ["Яковлев", "ёлкин", "Борисов", "Ежов", "арбузов", "Ёлкина"]
    async with unit_of_work() as s:
        for vk_id, name in enumerate(names, start=500):
            await users.add_app_user(s, vk_id, name, UserRole.SELLER)
    async with unit_of_work() as s:
        ordered = [u.display_name for u in await users.active_users(s)]
    assert ordered == ["арбузов", "Борисов", "Ежов", "ёлкин", "Ёлкина", "Яковлев"]
