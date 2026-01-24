"""
Message templates for the VK bot.

Provides script generation and formatted messages.
"""

from typing import List
from collections import defaultdict

from models.seat_assignment import SeatAssignment
from bot.config import SEAT_PRICE


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
