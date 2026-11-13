"""
Message templates for the VK bot.

Provides script generation and formatted messages.
"""

from collections import defaultdict
from decimal import Decimal
from itertools import groupby

from bot.config import SEAT_PRICE
from bot.utils.formatting import format_seat_ranges, pluralize_seats
from models.base import SeatStatus
from models.seat_assignment import SeatAssignment


def generate_reservation_script(
    buyer_display_name: str,
    seats: list[SeatAssignment],
) -> str:
    """
    Generate script for sending to customer.

    Args:
        buyer_display_name: Customer's display name
        seats: List of SeatAssignment for the reservation

    Returns:
        Formatted script text
    """
    if not seats:
        return "Ошибка: нет мест в брони"

    # Group seats by row
    seats_by_row = defaultdict(list)
    for seat in seats:
        seats_by_row[seat.row_number].append(seat.seat_number)

    # Sort rows and seats
    sorted_rows = sorted(seats_by_row.keys())

    # Build seat list text
    seat_lines = []
    for row in sorted_rows:
        row_seats = sorted(seats_by_row[row])
        seats_str = ", ".join(map(str, row_seats))
        seat_lines.append(f"Ряд {row}, места {seats_str}")

    seats_text = "\n".join(seat_lines)

    # Calculate total
    total_seats = len(seats)
    total_price = total_seats * SEAT_PRICE

    # Generate script
    script = f"""Места забронированы.

Ваша бронь:
{seats_text}

Всего {total_seats} {pluralize_seats(total_seats)}.
К оплате: {total_price} руб.

Спасибо за бронь!
"""

    return script


def format_seat_list(seats: list[SeatAssignment]) -> str:
    """
    Format seat list as text.

    Args:
        seats: List of SeatAssignment

    Returns:
        Formatted text with rows and seats
    """
    if not seats:
        return "Нет мест"

    seats_by_row = defaultdict(list)
    for seat in seats:
        seats_by_row[seat.row_number].append(seat.seat_number)

    lines = []
    for row in sorted(seats_by_row.keys()):
        row_seats = sorted(seats_by_row[row])
        seats_str = ", ".join(map(str, row_seats))
        lines.append(f"Ряд {row}, места: {seats_str}")

    return "\n".join(lines)


def format_reservation_seats(seats: list[SeatAssignment]) -> str:
    """
    Format all seats grouped by row and status, with emoji indicators.

    Returns formatted text:
    Всего мест: 12 | Бронь: 8 | Оплачено: 4

    Ряд 5: 1-3, 5 📌Бронь
    Ряд 5: 7-9 ✅Оплачено
    Ряд 6: 2, 4-6 📌Бронь

    Args:
        seats: List of SeatAssignment objects

    Returns:
        Formatted string with summary and seat groups
    """
    if not seats:
        return "Нет мест"

    # Count by status
    status_counts = defaultdict(int)
    for seat in seats:
        status_counts[seat.status] += 1

    # Summary line
    total = len(seats)
    booked = status_counts[SeatStatus.BOOKED]
    paid = status_counts[SeatStatus.PAID]
    reserved = status_counts[SeatStatus.RESERVED]

    summary = f"Всего: {total} {pluralize_seats(total)}"
    if booked:
        summary += f" | 📌Бронь: {booked}"
    if paid:
        summary += f" | ✅Оплачено: {paid}"
    if reserved:
        summary += f" | 🔒Резерв: {reserved}"

    # Group by row and status
    # CRITICAL: Must sort before groupby - groupby only groups consecutive elements
    seats_sorted = sorted(seats, key=lambda s: (s.row_number, s.status.value, s.seat_number))

    lines = [summary, ""]

    for row_num, row_group in groupby(seats_sorted, key=lambda s: s.row_number):
        row_seats = list(row_group)

        # Further group by status within row
        for status, status_group in groupby(row_seats, key=lambda s: s.status):
            seat_numbers = [s.seat_number for s in status_group]
            seat_range = format_seat_ranges(seat_numbers)

            # Status emoji
            if status == SeatStatus.BOOKED:
                status_text = "📌Бронь"
            elif status == SeatStatus.PAID:
                status_text = "✅Оплачено"
            else:  # RESERVED
                status_text = "🔒Резерв"

            lines.append(f"Ряд {row_num}, места: {seat_range} {status_text}")

    return "\n".join(lines)


def format_reserves_list(reserves: list) -> str:
    """
    Format active reserves list for /reserve command display.

    Args:
        reserves: List of dicts from db.get_active_reserves()
                  Each dict has: row, seats (list[int]), note

    Returns:
        Formatted multi-line string
    """
    if not reserves:
        return "Активных резервов нет."

    total_seats = sum(len(r["seats"]) for r in reserves)
    lines = [f"🔒 Активные резервы ({total_seats} {pluralize_seats(total_seats)}):", ""]

    # Group consecutive entries by note for readability
    current_note = None
    for r in reserves:
        seats_str = format_seat_ranges(r["seats"])
        note = r["note"] or "без комментария"
        if note != current_note:
            if current_note is not None:
                lines.append("")  # blank line between groups
            lines.append(f"📌 {note}")
            current_note = note
        lines.append(f"  Ряд {r['row']:>2}, места: {seats_str}")

    return "\n".join(lines)


def format_debtors_list(debtors: list) -> str:
    """
    Format debtor list for /debtors command display.

    Args:
        debtors: List of debtor dicts from db.get_debtors()
                 Each dict has: buyer_display_name, booked_seat_count,
                 debt_amount, days_since_activity

    Returns:
        Formatted multi-line string with header and per-debtor details
    """
    count = len(debtors)
    lines = [f"Должники ({count}):", ""]

    for debtor in debtors:
        vk_id = debtor.get("buyer_vk_id")
        name = debtor["buyer_display_name"]
        header = f"{name} (vk.com/id{vk_id})" if vk_id else name
        lines.append(header)
        lines.append(
            f"  Мест: {debtor['booked_seat_count']} | "
            f"Долг: {debtor['debt_amount']} руб. | "
            f"Дней: {debtor['days_since_activity']}"
        )

    return "\n".join(lines)


def format_reminder(debtors: list) -> str:
    """
    Format compact debtor list for VK reminder messages sent to sellers.

    Args:
        debtors: List of debtor dicts from db.get_debtors()
                 Each dict has: buyer_display_name, buyer_vk_id,
                 booked_seat_count, debt_amount, days_since_activity

    Returns:
        Formatted multi-line string with header and compact per-debtor entries
    """
    count = len(debtors)
    lines = [f"Напоминание о должниках ({count}):", ""]

    for debtor in debtors:
        vk_id = debtor.get("buyer_vk_id")
        name = debtor["buyer_display_name"]
        header = f"{name} (vk.com/id{vk_id})" if vk_id else name
        lines.append(
            f"{header} -- "
            f"{debtor['booked_seat_count']} {pluralize_seats(debtor['booked_seat_count'])}, "
            f"{debtor['debt_amount']} руб., "
            f"{debtor['days_since_activity']} дн. без активности"
        )

    return "\n".join(lines)


def format_payment_confirmation(
    paid_seats: list[SeatAssignment],
    remaining_seats: list[SeatAssignment],
    payment_amount: Decimal,
    buyer_display_name: str,
) -> str:
    """
    Format payment confirmation message.

    Shows paid seats grouped by row and any remaining unpaid seats.

    Args:
        paid_seats: SeatAssignment objects that were just marked PAID
        remaining_seats: SeatAssignment objects still BOOKED (not yet paid)
        payment_amount: Amount paid in rubles
        buyer_display_name: Customer's display name

    Returns:
        Formatted confirmation text
    """
    # Group paid seats by row
    paid_by_row: defaultdict = defaultdict(list)
    for seat in paid_seats:
        paid_by_row[seat.row_number].append(seat.seat_number)

    paid_lines = []
    for row in sorted(paid_by_row.keys()):
        seat_nums = sorted(paid_by_row[row])
        paid_lines.append(f"Ряд {row}: места {format_seat_ranges(seat_nums)}")

    result = (
        f"Оплата зарегистрирована для {buyer_display_name}.\n\n"
        f"Оплачено {len(paid_seats)} {pluralize_seats(len(paid_seats))}:\n"
        + "\n".join(paid_lines)
        + f"\n\nСумма: {payment_amount} руб."
    )

    if remaining_seats:
        remaining_by_row: defaultdict = defaultdict(list)
        for seat in remaining_seats:
            remaining_by_row[seat.row_number].append(seat.seat_number)

        remaining_lines = []
        for row in sorted(remaining_by_row.keys()):
            seat_nums = sorted(remaining_by_row[row])
            remaining_lines.append(f"Ряд {row}: места {format_seat_ranges(seat_nums)}")

        result += (
            f"\n\nОсталось к оплате: {len(remaining_seats)} {pluralize_seats(len(remaining_seats))}:\n"
            + "\n".join(remaining_lines)
        )
    else:
        result += "\n\nВсе места оплачены!"

    return result
