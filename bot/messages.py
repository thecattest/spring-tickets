"""
Message templates for the VK bot.

Provides script generation and formatted messages.
"""

from typing import List
from collections import defaultdict
from itertools import groupby

from models.seat_assignment import SeatAssignment
from models.base import SeatStatus
from bot.config import SEAT_PRICE
from bot.utils.formatting import format_seat_ranges


def generate_reservation_script(
    buyer_display_name: str,
    seats: List[SeatAssignment],
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
    script = f"""Бронь сохранена.

Скрипт для отправки клиенту:

─────────────────────
Добрый день, {buyer_display_name}! Ваша бронь:

{seats_text}

[Место для вашего текста]

Всего: {total_seats} {'место' if total_seats == 1 else 'мест' if total_seats < 5 else 'мест'}
К оплате: {total_price} руб.

Спасибо за бронь!
─────────────────────

Скопируйте текст выше и отправьте клиенту.
"""

    return script


def format_seat_list(seats: List[SeatAssignment]) -> str:
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
        lines.append(f"Ряд {row}: {seats_str}")

    return "\n".join(lines)


def format_reservation_seats(seats: List[SeatAssignment]) -> str:
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

    summary = f"Всего мест: {total}"
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

            lines.append(f"Ряд {row_num}: {seat_range} {status_text}")

    return "\n".join(lines)
