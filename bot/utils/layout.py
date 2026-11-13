"""
Hall layout loading and validation.

Loads layout.json and provides validation functions for row and seat numbers.
The layout is cached in memory after first load.
"""

import json
import logging
from typing import Dict, Optional
from pathlib import Path

from bot.config import LAYOUT_FILE

logger = logging.getLogger(__name__)

# Global layout cache
_layout_cache: Optional[Dict] = None


class LayoutError(Exception):
    """Exception raised for layout-related errors."""
    pass


def load_layout() -> Dict:
    """
    Load hall layout from layout.json.

    Returns:
        Layout dictionary with rows configuration

    Raises:
        LayoutError: If layout file cannot be loaded or is invalid
    """
    global _layout_cache

    if _layout_cache is not None:
        return _layout_cache

    try:
        with open(LAYOUT_FILE, 'r', encoding='utf-8') as f:
            layout = json.load(f)

        # Validate layout structure
        if "rows" not in layout:
            raise LayoutError("Layout must contain 'rows' key")

        rows = layout["rows"]
        if not isinstance(rows, dict):
            raise LayoutError("Layout 'rows' must be a dictionary")

        # Validate each row has seatCount
        for row_num, row_data in rows.items():
            if "seatCount" not in row_data:
                raise LayoutError(f"Row {row_num} missing 'seatCount'")

            if not isinstance(row_data["seatCount"], int) or row_data["seatCount"] <= 0:
                raise LayoutError(f"Row {row_num} has invalid seatCount: {row_data['seatCount']}")

        _layout_cache = layout
        logger.info(f"Layout loaded: {len(rows)} rows")

        return layout

    except FileNotFoundError:
        raise LayoutError(f"Layout file not found: {LAYOUT_FILE}")
    except json.JSONDecodeError as e:
        raise LayoutError(f"Invalid JSON in layout file: {e}")


def get_layout() -> Dict:
    """
    Get cached layout (loads if not already loaded).

    Returns:
        Layout dictionary
    """
    if _layout_cache is None:
        return load_layout()
    return _layout_cache


def get_seat_count(row: int) -> int:
    """
    Get number of seats in a row.

    Args:
        row: Row number

    Returns:
        Number of seats in the row

    Raises:
        LayoutError: If row number is invalid
    """
    layout = get_layout()
    rows = layout["rows"]

    row_key = str(row)
    if row_key not in rows:
        raise LayoutError(f"Invalid row number: {row}")

    return rows[row_key]["seatCount"]


def is_valid_row(row: int) -> bool:
    """
    Check if row number is valid.

    Args:
        row: Row number to validate

    Returns:
        True if row exists, False otherwise
    """
    try:
        layout = get_layout()
        rows = layout["rows"]
        return str(row) in rows
    except LayoutError:
        return False


def is_valid_seat(row: int, seat: int) -> bool:
    """
    Check if seat number is valid for given row.

    Args:
        row: Row number
        seat: Seat number

    Returns:
        True if seat exists in the row, False otherwise
    """
    try:
        seat_count = get_seat_count(row)
        return 1 <= seat <= seat_count
    except LayoutError:
        return False


def get_row_range() -> tuple[int, int]:
    """
    Get valid row number range.

    Returns:
        Tuple of (min_row, max_row)
    """
    layout = get_layout()
    rows = layout["rows"]
    row_numbers = [int(r) for r in rows.keys()]
    return min(row_numbers), max(row_numbers)


def clear_cache():
    """
    Clear layout cache (useful for testing).
    """
    global _layout_cache
    _layout_cache = None
    logger.debug("Layout cache cleared")
