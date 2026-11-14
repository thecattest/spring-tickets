"""
Сервисы: транзакции и исправления этапа 6 (ROADMAP) — атомарность, блокировка
при оплате, конфликт мест при гонке, неактивная бронь, аудит в транзакции.
"""

import threading
import time

import pytest
from sqlalchemy import func, select

from tickets.bot.utils import db as bot_db
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


@pytest.fixture
def seller_id() -> int:
    with unit_of_work() as s:
        return users.add_app_user(s, 201, "Билетёр", UserRole.SELLER).id


def new_reservation(seller_id: int, buyer_vk_id: int, row: int, seat_list: list[int]) -> int:
    with unit_of_work() as s:
        buyer = users.get_or_create_vk_user(s, buyer_vk_id, f"Покупатель {buyer_vk_id}")
        reservation = reservations.create(s, buyer.id, seller_id)
        if seat_list:
            reservations.add_seats(s, reservation.id, row, seat_list, seller_id)
        return reservation.id


def count(model, *where) -> int:
    with unit_of_work() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


def active_seats(status: SeatStatus | None = None) -> int:
    where = [SeatAssignment.released_at.is_(None)]
    if status is not None:
        where.append(SeatAssignment.status == status)
    return count(SeatAssignment, *where)


# --- атомарность и аудит ----------------------------------------------------


def test_failure_rolls_back_whole_operation(seller_id, monkeypatch):
    """Упала запись аудита — мест тоже нет: операция целиком или никак."""
    rid = new_reservation(seller_id, 301, 5, [])

    def broken_log(*args, **kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(audit, "log", broken_log)
    with pytest.raises(RuntimeError), unit_of_work() as s:
        reservations.add_seats(s, rid, 5, [1, 2, 3], seller_id)
    assert active_seats() == 0


def test_audit_written_with_the_change(seller_id):
    rid = new_reservation(seller_id, 301, 5, [1, 2])
    assert count(AuditLog, AuditLog.action_type == audit.AuditAction.SEATS_ADDED.value) == 1
    assert count(AuditLog, AuditLog.entity_id == str(rid)) == 2  # создание + места


# --- неактивная бронь -------------------------------------------------------


def test_cancelled_reservation_rejects_changes(seller_id):
    rid = new_reservation(seller_id, 301, 5, [1, 2])
    with unit_of_work() as s:
        reservations.cancel(s, rid, seller_id, is_admin=False)

    for change in (
        lambda s: reservations.add_seats(s, rid, 5, [3], seller_id),
        lambda s: reservations.remove_seats(s, rid, 5, [1], seller_id),
        lambda s: payments.record(s, rid, 1, seller_id),
        lambda s: reservations.cancel(s, rid, seller_id, is_admin=True),
    ):
        with pytest.raises(ReservationNotActiveError), unit_of_work() as s:
            change(s)
    assert active_seats() == 0


def test_facade_keeps_old_exception_names(seller_id):
    """Хендлеры ловят db.DatabaseError — новые ошибки сервисов тоже под ним."""
    rid = new_reservation(seller_id, 301, 5, [])
    with unit_of_work() as s:
        reservations.cancel(s, rid, seller_id, is_admin=False)
    with pytest.raises(bot_db.DatabaseError):
        bot_db.add_seats_to_reservation(rid, 5, [1], seller_id)


# --- конфликт мест ----------------------------------------------------------


def test_occupied_seat_is_refused(seller_id):
    new_reservation(seller_id, 301, 5, [3, 4])
    rid2 = new_reservation(seller_id, 302, 5, [])
    with pytest.raises(SeatOccupiedError) as error, unit_of_work() as s:
        reservations.add_seats(s, rid2, 5, [4, 5], seller_id)
    assert [c["seat"] for c in error.value.conflicts] == [4]
    assert active_seats() == 2  # место 5 тоже не добавлено


def test_seat_taken_in_parallel_is_seat_occupied_not_db_error(seller_id, monkeypatch):
    """
    Место заняли между проверкой и вставкой: срабатывает уникальный индекс —
    результат SeatOccupiedError с перечитанными конфликтами, а не DatabaseError.
    """
    new_reservation(seller_id, 301, 5, [4])
    rid2 = new_reservation(seller_id, 302, 5, [])

    real_find = seats.find_conflicts
    calls = []

    def stale_check(session, row, seat_list):
        calls.append(row)
        # Первая проверка «не видит» параллельную бронь — как при гонке
        return [] if len(calls) == 1 else real_find(session, row, seat_list)

    monkeypatch.setattr(seats, "find_conflicts", stale_check)
    with pytest.raises(SeatOccupiedError) as error, unit_of_work() as s:
        reservations.add_seats(s, rid2, 5, [4, 5], seller_id)
    assert [c["seat"] for c in error.value.conflicts] == [4]
    assert active_seats() == 1


# --- гонка при оплате -------------------------------------------------------


def test_concurrent_payments_of_one_reservation_are_serialized(seller_id):
    """
    Две оплаты одной брони одновременно: вторая ждёт блокировку первой
    (FOR UPDATE) и после её коммита видит, что оплачивать уже нечего.
    """
    rid = new_reservation(seller_id, 301, 5, [1, 2, 3])
    first_paid, first_may_commit = threading.Event(), threading.Event()
    second_done = threading.Event()
    outcome: dict[str, object] = {}

    def first():
        with unit_of_work() as s:
            payments.record(s, rid, 2, seller_id)
            first_paid.set()
            first_may_commit.wait(10)  # транзакция открыта, бронь заблокирована

    def second():
        first_paid.wait(10)
        try:
            with unit_of_work() as s:
                payments.record(s, rid, 2, seller_id)
            outcome["second"] = "paid"
        except InsufficientSeatsError as e:
            outcome["second"] = ("insufficient", e.available)
        finally:
            second_done.set()

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for t in threads:
        t.start()

    first_paid.wait(10)
    time.sleep(0.5)
    assert not second_done.is_set(), "вторая оплата должна ждать блокировку брони"
    first_may_commit.set()
    for t in threads:
        t.join(10)

    assert outcome["second"] == ("insufficient", 1)  # осталось одно неоплаченное
    assert count(Payment) == 1
    assert active_seats(SeatStatus.PAID) == 2
