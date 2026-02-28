"""
Formatting utilities for seat displays.

Provides range formatting for consecutive seat numbers.
"""

from itertools import groupby
from operator import itemgetter


__all__ = ["format_seat_ranges", "pluralize_seats"]


def pluralize_seats(n: int) -> str:
    """Склонение слова 'место': 1 место, 2 места, 5 мест."""
    abs_n = abs(n) % 100
    last_one = abs_n % 10
    if 11 <= abs_n <= 19:
        return "мест"
    if last_one == 1:
        return "место"
    if 2 <= last_one <= 4:
        return "места"
    return "мест"


def format_seat_ranges(seats: list[int]) -> str:
    """
    Format consecutive seats as ranges.

    Args:
        seats: Sorted list of seat numbers

    Returns:
        Formatted string like "1-3, 5, 7-9"

    Examples:
        [1, 2, 3, 5, 7, 8, 9] -> "1-3, 5, 7-9"
        [5] -> "5"
        [] -> ""
    """
    if not seats:
        return ""

    ranges = []
    # The groupby trick: enumerate(seats) pairs each seat with its index.
    # For consecutive seats, index - seat_number remains constant, so they group together.
    for _, g in groupby(enumerate(seats), lambda t: t[0] - t[1]):
        group = list(map(itemgetter(1), g))
        if len(group) == 1:
            ranges.append(str(group[0]))
        else:
            ranges.append(f"{group[0]}-{group[-1]}")

    return ", ".join(ranges)
