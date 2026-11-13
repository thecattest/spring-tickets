"""
bot/steps.py — Pure input validation primitives shared across handler files.

These functions accept raw text and return typed result dataclasses (RowResult,
SeatResult). Handlers inspect the result and send replies accordingly.

Steps are pure: no side effects, no I/O calls, no state transitions.
All functions are fully synchronous — no async, no await.
"""

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class RowResult:
    ok: bool
    row: int | None = None
    error_text: str | None = None


@dataclass
class SeatResult:
    ok: bool
    seats: list[int] | None = None
    error_text: str | None = None


def handle_row_input(text: str) -> RowResult:
    from bot import texts
    from bot.utils.layout import get_row_range, is_valid_row

    stripped = text.strip()
    try:
        row = int(stripped)
    except ValueError:
        min_row, max_row = get_row_range()
        return RowResult(ok=False, error_text=texts.ERR_INVALID_ROW_FORMAT.format(
            min_row=min_row, max_row=max_row
        ))

    if not is_valid_row(row):
        min_row, max_row = get_row_range()
        return RowResult(ok=False, error_text=texts.ERR_INVALID_ROW.format(
            min_row=min_row, max_row=max_row
        ))

    return RowResult(ok=True, row=row)


def handle_seat_input(
    text: str,
    row: int,
    mode: Literal["layout_only", "availability", "membership"],
    reservation_id: int | None = None,
) -> SeatResult:
    from bot import texts
    from bot.utils.layout import get_seat_count, is_valid_seat
    from bot.utils.seat_parser import SeatParseError, parse_seats

    # Step 1: Parse
    try:
        seats = parse_seats(text.strip())
    except SeatParseError as e:
        return SeatResult(ok=False, error_text=texts.ERR_PARSE_INPUT.format(error=str(e)))

    # Step 2: Layout validation (all modes)
    seat_count = get_seat_count(row)
    invalid = [s for s in seats if not is_valid_seat(row, s)]
    if invalid:
        return SeatResult(
            ok=False,
            error_text=texts.ERR_INVALID_SEATS.format(
                seats=", ".join(map(str, invalid)),
                row=row,
                seat_count=seat_count,
            ),
        )

    # Step 3: Mode-specific validation
    if mode == "layout_only":
        return SeatResult(ok=True, seats=seats)

    if mode == "availability":
        from bot.utils import db
        from bot.utils.formatting import format_seat_ranges
        occupied_seats = []
        for seat in seats:
            assignment = db.get_seat_assignment(row, seat)
            if assignment:
                occupied_seats.append(seat)
        if occupied_seats:
            seats_str = format_seat_ranges(sorted(occupied_seats))
            return SeatResult(
                ok=False,
                error_text=f"Места {seats_str} в ряду {row} недоступны.\n\nВведите другие места:"
            )
        return SeatResult(ok=True, seats=seats)

    if mode == "membership":
        from bot.utils import db
        from models.base import SeatStatus
        all_reservation_seats = db.get_reservation_seats(reservation_id)
        seat_map = {(s.row_number, s.seat_number): s for s in all_reservation_seats}

        not_in_reservation = [s for s in seats if (row, s) not in seat_map]
        if not_in_reservation:
            return SeatResult(
                ok=False,
                error_text=texts.MSG_SEATS_NOT_IN_BOOKING.format(
                    seats=", ".join(map(str, not_in_reservation))
                ),
            )

        paid_seats = [s for s in seats if seat_map[(row, s)].status == SeatStatus.PAID]
        if paid_seats:
            return SeatResult(
                ok=False,
                error_text=texts.MSG_SEATS_ALREADY_PAID.format(
                    seats=", ".join(map(str, paid_seats))
                ),
            )

        return SeatResult(ok=True, seats=seats)

    raise ValueError(f"Unknown mode: {mode}")


def handle_confirmation(text: str) -> bool | None:
    from bot.constants import Btn
    stripped = text.strip()
    if stripped == Btn.CONFIRM:
        return True
    if stripped == Btn.CANCEL:
        return False
    return None
