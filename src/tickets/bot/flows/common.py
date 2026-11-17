"""Общие шаги сценариев: ввод ряда и мест, клиент в контексте, актуальность брони."""

import logging
from typing import Literal

from vkbottle.bot import Message

from tickets.bot import texts, vk
from tickets.bot.constants import Btn
from tickets.bot.fsm.context import Client, Context
from tickets.bot.fsm.storage import RedisStorage
from tickets.bot.utils.seat_parser import SeatParseError, parse_seats
from tickets.db import unit_of_work
from tickets.formatting import format_seat_ranges, pluralize_seats
from tickets.hall import get_row_range, get_seat_count, is_valid_row, is_valid_seat
from tickets.models.base import SeatStatus
from tickets.services import reservations, seats

logger = logging.getLogger(__name__)


# --- ввод -------------------------------------------------------------------


class InvalidInput(Exception):
    """Ввод не подходит; текст исключения — что ответить пользователю."""


def parse_row(text: str) -> int:
    min_row, max_row = get_row_range()
    try:
        row = int(text.strip())
    except ValueError:
        raise InvalidInput(
            texts.ERR_INVALID_ROW_FORMAT.format(min_row=min_row, max_row=max_row)
        ) from None
    if not is_valid_row(row):
        raise InvalidInput(texts.ERR_INVALID_ROW.format(min_row=min_row, max_row=max_row))
    return row


async def parse_seat_list(
    text: str,
    row: int,
    mode: Literal["layout_only", "availability", "membership"],
    reservation_id: int | None = None,
) -> list[int]:
    """
    Места в ряду: формат и геометрия зала (все режимы), затем
    availability — все свободны; membership — все из брони (reservation_id)
    и не оплачены. Не подходит — InvalidInput.
    """
    try:
        seat_list = parse_seats(text.strip())
    except SeatParseError as e:
        raise InvalidInput(texts.ERR_PARSE_INPUT.format(error=str(e))) from None

    invalid = [s for s in seat_list if not is_valid_seat(row, s)]
    if invalid:
        raise InvalidInput(
            texts.ERR_INVALID_SEATS.format(
                seats=", ".join(map(str, invalid)), row=row, seat_count=get_seat_count(row)
            )
        )
    if mode == "layout_only":
        return seat_list

    if mode == "availability":
        async with unit_of_work() as session:
            conflicts = await seats.find_conflicts(session, row, seat_list)
        if conflicts:
            taken = format_seat_ranges(sorted(c["seat"] for c in conflicts))
            raise InvalidInput(f"Места {taken} в ряду {row} недоступны.\n\nВведите другие места:")
        return seat_list

    if reservation_id is None:
        raise ValueError("membership mode needs reservation_id")
    async with unit_of_work() as session:
        by_seat = {
            (s.row_number, s.seat_number): s
            for s in await seats.of_reservation(session, reservation_id)
        }
    missing = [s for s in seat_list if (row, s) not in by_seat]
    if missing:
        raise InvalidInput(
            texts.MSG_SEATS_NOT_IN_BOOKING.format(seats=", ".join(map(str, missing)))
        )
    paid = [s for s in seat_list if by_seat[(row, s)].status == SeatStatus.PAID]
    if paid:
        raise InvalidInput(texts.MSG_SEATS_ALREADY_PAID.format(seats=", ".join(map(str, paid))))
    return seat_list


# Ответы на подтверждения: кнопки и то же самое текстом, без учёта регистра.
# «Отмена» как кнопку перехватывает команда /cancel ещё в роутере — сюда
# доходит «нет», набранное текстом; сценарии обрабатывают его так же (шаг назад)
_YES = {Btn.CONFIRM.lower(), Btn.YES.lower()}
_NO = {Btn.CANCEL.lower(), Btn.NO.lower()}


def parse_confirmation(text: str) -> bool | None:
    """«Подтвердить» / «да» — True, «Отмена» / «нет» — False, другое — None."""
    answer = text.strip().lower()
    if answer in _YES:
        return True
    if answer in _NO:
        return False
    return None


# --- контекст и бронь -------------------------------------------------------


async def require_client(
    message: Message, storage: RedisStorage, context: Context, lost_text: str
) -> Client | None:
    """Клиент из контекста; потерян — ответ lost_text, сброс и None."""
    if context.client is None:
        await vk.answer(message, lost_text)
        await storage.reset(message.from_id)
    return context.client


async def require_active(message: Message, storage: RedisStorage, client: Client) -> bool:
    """
    Бронь клиента ещё активна (её могли отменить с другого аккаунта, пока
    билетёр был в сценарии). Нет — сообщение, сброс и False (этап 6 ROADMAP).
    """
    async with unit_of_work() as session:
        if await reservations.is_active(session, client.reservation_id):
            return True
    await vk.answer(message, texts.MSG_RESERVATION_NOT_ACTIVE.format(id=client.reservation_id))
    await storage.reset(message.from_id)
    return False


async def seat_conflicts_text(conflicts: list[dict], tail: str) -> str:
    """Список занятых мест с тем, кем заняты; tail — последняя строка-подсказка."""
    lines = ["Места уже заняты:"]
    async with unit_of_work() as session:
        for c in conflicts:
            if c["status"] == SeatStatus.RESERVED:
                status, detail = "Резерв", c["note"] or "без комментария"
            else:
                status = "Бронь" if c["status"] == SeatStatus.BOOKED else "Оплачено"
                total = len(await seats.of_reservation(session, c["reservation_id"]))
                detail = f"бронь #{c['reservation_id']}, всего: {total} {pluralize_seats(total)}"
            lines.append(f"• Ряд {c['row']}, место {c['seat']} — {status} ({detail})")
    lines.append(f"\n{tail}")
    return "\n".join(lines)
