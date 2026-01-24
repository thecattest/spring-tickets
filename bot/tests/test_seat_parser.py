"""
Unit tests for seat parser.

Tests all supported input formats:
- Space-separated
- Comma-separated
- Ranges
- Mixed formats
- Error cases
"""

import pytest
from bot.utils.seat_parser import parse_seats, SeatParseError


class TestSeatParser:
    """Test seat input parsing."""

    def test_space_separated(self):
        """Test space-separated seat numbers."""
        assert parse_seats("5 6 7") == [5, 6, 7]
        assert parse_seats("10 11 12") == [10, 11, 12]
        assert parse_seats("1 2 3 4 5") == [1, 2, 3, 4, 5]

    def test_comma_separated(self):
        """Test comma-separated seat numbers."""
        assert parse_seats("5, 6, 7") == [5, 6, 7]
        assert parse_seats("10,11,12") == [10, 11, 12]
        assert parse_seats("1, 2, 3, 4, 5") == [1, 2, 3, 4, 5]

    def test_range(self):
        """Test range notation."""
        assert parse_seats("5-7") == [5, 6, 7]
        assert parse_seats("1-5") == [1, 2, 3, 4, 5]
        assert parse_seats("10-15") == [10, 11, 12, 13, 14, 15]

    def test_mixed_formats(self):
        """Test combination of formats."""
        assert parse_seats("1, 3, 5-7") == [1, 3, 5, 6, 7]
        assert parse_seats("1-3, 5, 7-9") == [1, 2, 3, 5, 7, 8, 9]
        assert parse_seats("1 3 5-7") == [1, 3, 5, 6, 7]
        assert parse_seats("1-3, 5 7-9") == [1, 2, 3, 5, 7, 8, 9]

    def test_whitespace_handling(self):
        """Test handling of extra whitespace."""
        assert parse_seats("  5  ,  6  ,  7  ") == [5, 6, 7]
        assert parse_seats("5,    6,    7") == [5, 6, 7]
        assert parse_seats("  1-3  ,  5  ") == [1, 2, 3, 5]

    def test_duplicate_removal(self):
        """Test that duplicates are removed."""
        assert parse_seats("5 5 6 6 7") == [5, 6, 7]
        assert parse_seats("1-3, 2-4") == [1, 2, 3, 4]
        assert parse_seats("5, 5, 5") == [5]

    def test_sorting(self):
        """Test that results are sorted."""
        assert parse_seats("7 5 6") == [5, 6, 7]
        assert parse_seats("10, 5, 7") == [5, 7, 10]
        assert parse_seats("5-7, 1-3") == [1, 2, 3, 5, 6, 7]

    def test_overlapping_ranges(self):
        """Test overlapping ranges."""
        assert parse_seats("3-5, 4-6") == [3, 4, 5, 6]
        assert parse_seats("1-10, 5-15") == list(range(1, 16))

    def test_single_seat(self):
        """Test single seat input."""
        assert parse_seats("5") == [5]
        assert parse_seats("  10  ") == [10]

    def test_large_numbers(self):
        """Test with larger seat numbers."""
        assert parse_seats("25 26 27 28") == [25, 26, 27, 28]
        assert parse_seats("20-28") == list(range(20, 29))

    # Error cases

    def test_empty_input(self):
        """Test empty input raises error."""
        with pytest.raises(SeatParseError, match="не может быть пустым"):
            parse_seats("")
        with pytest.raises(SeatParseError, match="не может быть пустым"):
            parse_seats("   ")

    def test_invalid_characters(self):
        """Test invalid characters raise error."""
        with pytest.raises(SeatParseError, match="Неверный формат"):
            parse_seats("abc")
        with pytest.raises(SeatParseError, match="Неверный формат"):
            parse_seats("5, 6, abc")
        with pytest.raises(SeatParseError, match="Неверный формат"):
            parse_seats("5@6")

    def test_incomplete_range(self):
        """Test incomplete range raises error."""
        with pytest.raises(SeatParseError, match="Неверный диапазон"):
            parse_seats("5-")
        with pytest.raises(SeatParseError, match="Неверный диапазон"):
            parse_seats("-5")

    def test_reversed_range(self):
        """Test reversed range raises error."""
        with pytest.raises(SeatParseError, match="больше конца"):
            parse_seats("7-5")
        with pytest.raises(SeatParseError, match="больше конца"):
            parse_seats("10-1")

    def test_zero_seat(self):
        """Test zero seat number raises error."""
        with pytest.raises(SeatParseError, match="положительными"):
            parse_seats("0")
        with pytest.raises(SeatParseError, match="положительными"):
            parse_seats("0-5")
        with pytest.raises(SeatParseError, match="положительными"):
            parse_seats("5-0")

    def test_negative_seat(self):
        """Test negative seat number raises error."""
        with pytest.raises(SeatParseError, match="Неверный формат"):
            parse_seats("-1")
        with pytest.raises(SeatParseError, match="Неверный формат"):
            parse_seats("5, -3")

    def test_triple_range(self):
        """Test triple range raises error."""
        with pytest.raises(SeatParseError, match="Неверный диапазон"):
            parse_seats("5-7-9")

    def test_double_hyphen(self):
        """Test double hyphen raises error."""
        with pytest.raises(SeatParseError, match="Неверный диапазон"):
            parse_seats("5--7")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
