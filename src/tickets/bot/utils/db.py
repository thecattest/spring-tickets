"""
Слой данных для хендлеров бота — временный фасад над tickets.services.

Каждая функция — async и одна транзакция (unit_of_work) вокруг вызова сервиса: операция
атомарна, аудит пишется в той же транзакции. Имена функций и исключений —
прежние, хендлеры пока не меняются; на шаге 5 этапа 7 (ROADMAP) хендлеры сами
откроют unit_of_work и вызовут сервисы, а этот модуль удалится.

Ошибки: бизнес-правила — исключения tickets.services.errors (здесь под старыми
именами); неожиданные ошибки SQLAlchemy — DatabaseError, как и раньше
(хендлеры показывают «ошибка, попробуйте ещё раз»).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from tickets.db import unit_of_work
from tickets.models.base import UserRole
from tickets.models.payment import Payment
from tickets.models.reservation import Reservation
from tickets.models.seat_assignment import SeatAssignment
from tickets.models.user import AppUser
from tickets.models.vk_user import VkUser
from tickets.services import payments, reports, reservations, seats, users
from tickets.services.errors import (
    InsufficientSeatsError,
    NotAllowedError,
    ReservationNotActiveError,
    SeatOccupiedError,
    ServiceError,
)

logger = logging.getLogger(__name__)

# Прежние имена исключений — их ловят хендлеры
DatabaseError = ServiceError
PermissionError = NotAllowedError  # noqa: A001 — имя из старого API модуля

__all__ = [
    "DatabaseError",
    "InsufficientSeatsError",
    "PermissionError",
    "ReservationNotActiveError",
    "SeatOccupiedError",
]


@asynccontextmanager
async def _transaction() -> AsyncIterator[AsyncSession]:
    """unit_of_work + неожиданная ошибка базы → DatabaseError (контракт хендлеров)."""
    try:
        async with unit_of_work() as session:
            yield session
    except SQLAlchemyError as e:
        logger.exception("Database error")
        raise DatabaseError(f"Database error: {e}") from e


# --- пользователи -----------------------------------------------------------


async def get_or_create_vk_user(vk_id: int, display_name: str) -> VkUser:
    async with _transaction() as s:
        return await users.get_or_create_vk_user(s, vk_id, display_name)


async def get_seller_id(vk_user_id: int) -> int:
    """AppUser.id билетёра/админа; нет такого — PermissionError."""
    async with _transaction() as s:
        return (await users.require_app_user(s, vk_user_id)).id


async def get_app_user_by_vk_id(vk_user_id: int) -> AppUser | None:
    async with _transaction() as s:
        return await users.get_active_app_user(s, vk_user_id)


async def is_user_admin(vk_user_id: int) -> bool:
    async with _transaction() as s:
        return await users.is_admin(s, vk_user_id)


async def get_user_role(vk_user_id: int) -> UserRole | None:
    async with _transaction() as s:
        return await users.get_role(s, vk_user_id)


async def get_all_admin_vk_ids() -> list[int]:
    async with _transaction() as s:
        return await users.admin_vk_ids(s)


async def get_all_app_users() -> list[AppUser]:
    async with _transaction() as s:
        return await users.active_users(s)


async def get_all_active_sellers() -> list[AppUser]:
    async with _transaction() as s:
        return await users.active_sellers(s)


async def add_app_user(vk_user_id: int, display_name: str, role: UserRole) -> AppUser:
    async with _transaction() as s:
        return await users.add_app_user(s, vk_user_id, display_name, role)


async def deactivate_app_user(vk_user_id: int) -> None:
    async with _transaction() as s:
        await users.deactivate_app_user(s, vk_user_id)


# --- брони и места ----------------------------------------------------------


async def get_active_reservation(vk_user_id: int) -> Reservation | None:
    """vk_user_id — VkUser.id (не VK ID)."""
    async with _transaction() as s:
        return await reservations.get_active(s, vk_user_id)


async def create_reservation(buyer_vk_user_id: int, sold_by_user_id: int) -> Reservation:
    async with _transaction() as s:
        return await reservations.create(s, buyer_vk_user_id, sold_by_user_id)


async def add_seats_to_reservation(
    reservation_id: int, row: int, seats_list: list[int], user_id: int
) -> list[SeatAssignment]:
    async with _transaction() as s:
        return await reservations.add_seats(s, reservation_id, row, seats_list, user_id)


async def release_seats(reservation_id: int, row: int, seats_list: list[int], user_id: int) -> int:
    async with _transaction() as s:
        return await reservations.remove_seats(s, reservation_id, row, seats_list, user_id)


async def cancel_reservation(reservation_id: int, user_id: int, is_admin: bool) -> bool:
    async with _transaction() as s:
        await reservations.cancel(s, reservation_id, user_id, is_admin)
    return True


async def get_reservation_seats(reservation_id: int) -> list[SeatAssignment]:
    async with _transaction() as s:
        return await seats.of_reservation(s, reservation_id)


async def get_reservation_booked_seats_in_row(reservation_id: int, row: int) -> list[int]:
    async with _transaction() as s:
        return await seats.of_reservation_in_row(s, reservation_id, row)


async def is_seat_available(row: int, seat: int) -> bool:
    async with _transaction() as s:
        return await seats.is_available(s, row, seat)


async def get_seat_assignment(row: int, seat: int) -> SeatAssignment | None:
    async with _transaction() as s:
        return await seats.get_assignment(s, row, seat)


async def get_available_seats_in_row(row: int) -> list[int]:
    async with _transaction() as s:
        return await seats.available_in_row(s, row)


# --- оплаты -----------------------------------------------------------------


async def record_payment(
    reservation_id: int,
    seat_count: int,
    user_id: int,
    vk_message_url: str | None = None,
    vk_message_ts: datetime | None = None,
    receipt_attachments: str | None = None,
) -> tuple[Payment, list[SeatAssignment]]:
    async with _transaction() as s:
        return await payments.record(
            s,
            reservation_id,
            seat_count,
            user_id,
            vk_message_url=vk_message_url,
            vk_message_ts=vk_message_ts,
            receipt_attachments=receipt_attachments,
        )


# --- резервы ----------------------------------------------------------------


async def get_active_reserves() -> list[dict]:
    async with _transaction() as s:
        return await seats.active_reserves(s)


async def add_reserve(
    row: int, seats_list: list[int], comment: str, user_id: int
) -> list[SeatAssignment]:
    async with _transaction() as s:
        return await seats.add_reserve(s, row, seats_list, comment, user_id)


async def release_reserve(row: int, seats_list: list[int], user_id: int) -> list[dict]:
    async with _transaction() as s:
        return await seats.release_reserve(s, row, seats_list, user_id)


async def get_reserved_seats_in_row(row: int) -> list[int]:
    async with _transaction() as s:
        return await seats.reserved_in_row(s, row)


async def get_reserve_notes(row: int, seats_list: list[int]) -> dict[int, str | None]:
    async with _transaction() as s:
        return await seats.reserve_notes(s, row, seats_list)


# --- должники ---------------------------------------------------------------


async def get_debtors(seller_id: int | None = None, min_days: int = 0) -> list[dict]:
    async with _transaction() as s:
        return await reports.debtors(s, seller_id=seller_id, min_days=min_days)


async def log_reminder_sent(seller_id: int, debtor_count: int) -> None:
    async with _transaction() as s:
        await reports.log_reminder_sent(s, seller_id, debtor_count)
