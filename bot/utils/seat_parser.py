"""
Seat input parser.

Supports multiple input formats:
- Spaces: "5 6 7" -> [5, 6, 7]
- Commas: "5, 6, 7" -> [5, 6, 7]
- Ranges: "5-7" -> [5, 6, 7]
- Mixed: "1, 3, 5-7" -> [1, 3, 5, 6, 7]
- Complex: "1-3, 5, 7-9" -> [1, 2, 3, 5, 7, 8, 9]
"""

import re
import logging
from typing import List

logger = logging.getLogger(__name__)


class SeatParseError(Exception):
    """Exception raised for seat parsing errors."""
    pass


def parse_seats(text: str) -> List[int]:
    """
    Parse seat numbers from text input.

    Supports formats:
    - Space-separated: "5 6 7"
    - Comma-separated: "5, 6, 7"
    - Ranges: "5-7"
    - Mixed: "1, 3, 5-7"

    Args:
        text: Input text containing seat numbers

    Returns:
        Sorted list of unique seat numbers

    Raises:
        SeatParseError: If input format is invalid
    """
    if not text or not text.strip():
        raise SeatParseError("Ввод не может быть пустым")

    text = text.strip()

    # Validate allowed characters: digits, spaces, commas, hyphens
    if not re.match(r'^[\d\s,\-]+$', text):
        raise SeatParseError(
            "Неверный формат. Используйте только цифры, пробелы, запятые и тире. "
            "Примеры: '5 6 7' или '5, 6, 7' или '5-7'"
        )

    # Normalize: replace commas with spaces, collapse multiple spaces
    normalized = re.sub(r'[,\s]+', ' ', text).strip()

    # Split by spaces
    parts = normalized.split(' ')

    seats = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Check if it's a range (e.g., "5-7")
        if '-' in part:
            try:
                range_parts = part.split('-')

                if len(range_parts) != 2:
                    raise SeatParseError(
                        f"Неверный диапазон: '{part}'. Используйте формат 'начало-конец', например '5-7'"
                    )

                start_str, end_str = range_parts

                if not start_str or not end_str:
                    raise SeatParseError(
                        f"Неверный диапазон: '{part}'. Начало и конец диапазона не могут быть пустыми"
                    )

                try:
                    start = int(start_str)
                    end = int(end_str)
                except ValueError:
                    raise SeatParseError(
                        f"Неверный диапазон: '{part}'. Начало и конец должны быть числами"
                    )

                if start <= 0 or end <= 0:
                    raise SeatParseError(
                        f"Неверный диапазон: '{part}'. Номера мест должны быть положительными"
                    )

                if start > end:
                    raise SeatParseError(
                        f"Неверный диапазон: '{part}'. Начало ({start}) больше конца ({end})"
                    )

                # Add all seats in range
                seats.extend(range(start, end + 1))

            except SeatParseError:
                raise
            except Exception as e:
                raise SeatParseError(f"Ошибка обработки диапазона '{part}': {e}")

        else:
            # Single seat number
            try:
                seat = int(part)

                if seat <= 0:
                    raise SeatParseError(
                        f"Неверный номер места: {seat}. Номера мест должны быть положительными"
                    )

                seats.append(seat)

            except ValueError:
                raise SeatParseError(f"Неверный номер места: '{part}'. Ожидается число")

    if not seats:
        raise SeatParseError("Не найдено ни одного номера места")

    # Remove duplicates and sort
    seats = sorted(set(seats))

    logger.debug(f"Parsed seats: {text} -> {seats}")

    return seats


if __name__ == "__main__":
    # Test cases
    logging.basicConfig(level=logging.DEBUG)

    test_cases = [
        ("5 6 7", [5, 6, 7]),
        ("5, 6, 7", [5, 6, 7]),
        ("5-7", [5, 6, 7]),
        ("1, 3, 5-7", [1, 3, 5, 6, 7]),
        ("1-3, 5, 7-9", [1, 2, 3, 5, 7, 8, 9]),
        ("10 11 12", [10, 11, 12]),
        ("  5  ,  6  ,  7  ", [5, 6, 7]),  # Extra spaces
        ("5,6,7", [5, 6, 7]),  # No spaces
        ("1 1 2 2 3", [1, 2, 3]),  # Duplicates
        ("3-5, 4-6", [3, 4, 5, 6]),  # Overlapping ranges
    ]

    print("Testing seat parser...")
    for input_text, expected in test_cases:
        try:
            result = parse_seats(input_text)
            status = "PASS" if result == expected else "FAIL"
            print(f"{status}: '{input_text}' -> {result} (expected {expected})")
        except SeatParseError as e:
            print(f"ERROR: '{input_text}' -> {e}")

    # Test error cases
    print("\nTesting error cases...")
    error_cases = [
        "",  # Empty
        "   ",  # Whitespace only
        "abc",  # Letters
        "5-",  # Incomplete range
        "-5",  # Invalid range
        "5--7",  # Double hyphen
        "7-5",  # Reversed range
        "0",  # Zero
        "-1",  # Negative
        "5-7-9",  # Triple range
    ]

    for input_text in error_cases:
        try:
            result = parse_seats(input_text)
            print(f"UNEXPECTED SUCCESS: '{input_text}' -> {result}")
        except SeatParseError as e:
            print(f"PASS: '{input_text}' -> {e}")
