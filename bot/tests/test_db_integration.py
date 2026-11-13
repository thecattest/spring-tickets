"""
Integration tests for database operations.

Tests:
- VK user creation
- Reservation creation
- Seat availability checking
- Seat assignment
- Conflict handling
"""

import pytest
from datetime import datetime

from models.base import Base, SeatStatus, ReservationState
from models.vk_user import VkUser
from models.user import AppUser, UserRole
from models.reservation import Reservation
from models.seat_assignment import SeatAssignment
from database import SessionLocal
from bot.utils import db


@pytest.fixture(scope="function")
def test_db():
    """
    Engine временной тестовой базы.

    Саму базу подменяет и очищает перед каждым тестом корневой conftest.py.

    Yields:
        Database engine
    """
    from database import engine
    yield engine


@pytest.fixture(scope="function")
def test_seller(test_db):
    """
    Create a test seller user.

    Returns:
        AppUser instance
    """
    with SessionLocal() as session:
        seller = AppUser(
            role=UserRole.SELLER,
            display_name="Test Seller",
            is_active=True,
        )
        session.add(seller)
        session.commit()
        session.refresh(seller)
        return seller


class TestVkUserOperations:
    """Test VK user database operations."""

    def test_create_vk_user(self, test_db):
        """Test creating new VK user."""
        vk_user = db.get_or_create_vk_user(12345, "Test User")

        assert vk_user.id is not None
        assert vk_user.vk_user_id == 12345
        assert vk_user.display_name == "Test User"

    def test_get_existing_vk_user(self, test_db):
        """Test getting existing VK user."""
        # Create user
        vk_user1 = db.get_or_create_vk_user(12345, "Test User")

        # Get same user
        vk_user2 = db.get_or_create_vk_user(12345, "Test User")

        assert vk_user1.id == vk_user2.id

    def test_update_vk_user_display_name(self, test_db):
        """Test updating VK user display name."""
        # Create user
        vk_user1 = db.get_or_create_vk_user(12345, "Old Name")

        # Update name
        vk_user2 = db.get_or_create_vk_user(12345, "New Name")

        assert vk_user1.id == vk_user2.id
        assert vk_user2.display_name == "New Name"


class TestReservationOperations:
    """Test reservation database operations."""

    def test_create_reservation(self, test_db, test_seller):
        """Test creating new reservation."""
        # Create VK user
        vk_user = db.get_or_create_vk_user(12345, "Test User")

        # Create reservation
        reservation = db.create_reservation(vk_user.id, test_seller.id)

        assert reservation.id is not None
        assert reservation.buyer_vk_user_id == vk_user.id
        assert reservation.sold_by_user_id == test_seller.id
        assert reservation.state == ReservationState.ACTIVE

    def test_get_active_reservation(self, test_db, test_seller):
        """Test getting active reservation."""
        # Create VK user and reservation
        vk_user = db.get_or_create_vk_user(12345, "Test User")
        reservation = db.create_reservation(vk_user.id, test_seller.id)

        # Get active reservation
        active = db.get_active_reservation(vk_user.id)

        assert active is not None
        assert active.id == reservation.id

    def test_no_active_reservation(self, test_db):
        """Test getting active reservation when none exists."""
        # Create VK user without reservation
        vk_user = db.get_or_create_vk_user(12345, "Test User")

        # Get active reservation
        active = db.get_active_reservation(vk_user.id)

        assert active is None


class TestSeatOperations:
    """Test seat assignment operations."""

    def test_seat_available(self, test_db):
        """Test checking seat availability."""
        assert db.is_seat_available(1, 5) is True

    def test_seat_occupied(self, test_db, test_seller):
        """Test checking occupied seat."""
        # Create reservation and add seat
        vk_user = db.get_or_create_vk_user(12345, "Test User")
        reservation = db.create_reservation(vk_user.id, test_seller.id)
        db.add_seats_to_reservation(reservation.id, 1, [5], test_seller.id)

        # Check seat is occupied
        assert db.is_seat_available(1, 5) is False

    def test_add_seats_to_reservation(self, test_db, test_seller):
        """Test adding seats to reservation."""
        # Create reservation
        vk_user = db.get_or_create_vk_user(12345, "Test User")
        reservation = db.create_reservation(vk_user.id, test_seller.id)

        # Add seats
        seats = db.add_seats_to_reservation(reservation.id, 1, [5, 6, 7], test_seller.id)

        assert len(seats) == 3
        assert all(s.reservation_id == reservation.id for s in seats)
        assert all(s.row_number == 1 for s in seats)
        assert [s.seat_number for s in seats] == [5, 6, 7]

    def test_add_seats_conflict(self, test_db, test_seller):
        """Test adding seats with conflict."""
        # Create first reservation and add seat
        vk_user1 = db.get_or_create_vk_user(12345, "User 1")
        reservation1 = db.create_reservation(vk_user1.id, test_seller.id)
        db.add_seats_to_reservation(reservation1.id, 1, [5], test_seller.id)

        # Create second reservation and try to add same seat
        vk_user2 = db.get_or_create_vk_user(67890, "User 2")
        reservation2 = db.create_reservation(vk_user2.id, test_seller.id)

        # Should raise SeatOccupiedError
        with pytest.raises(db.SeatOccupiedError) as exc_info:
            db.add_seats_to_reservation(reservation2.id, 1, [5], test_seller.id)

        assert len(exc_info.value.conflicts) == 1
        assert exc_info.value.conflicts[0]['row'] == 1
        assert exc_info.value.conflicts[0]['seat'] == 5

    def test_add_seats_atomic(self, test_db, test_seller):
        """Test that seat addition is atomic."""
        # Create reservation and add one seat
        vk_user1 = db.get_or_create_vk_user(12345, "User 1")
        reservation1 = db.create_reservation(vk_user1.id, test_seller.id)
        db.add_seats_to_reservation(reservation1.id, 1, [5], test_seller.id)

        # Create second reservation
        vk_user2 = db.get_or_create_vk_user(67890, "User 2")
        reservation2 = db.create_reservation(vk_user2.id, test_seller.id)

        # Try to add multiple seats where one is occupied
        try:
            db.add_seats_to_reservation(reservation2.id, 1, [4, 5, 6], test_seller.id)
        except db.SeatOccupiedError:
            pass

        # Verify no seats were added (atomicity)
        assert db.is_seat_available(1, 4) is True
        assert db.is_seat_available(1, 5) is False
        assert db.is_seat_available(1, 6) is True

    def test_get_reservation_seats(self, test_db, test_seller):
        """Test getting all seats for reservation."""
        # Create reservation and add seats from multiple rows
        vk_user = db.get_or_create_vk_user(12345, "Test User")
        reservation = db.create_reservation(vk_user.id, test_seller.id)

        db.add_seats_to_reservation(reservation.id, 1, [5, 6, 7], test_seller.id)
        db.add_seats_to_reservation(reservation.id, 2, [10, 11], test_seller.id)

        # Get all seats
        seats = db.get_reservation_seats(reservation.id)

        assert len(seats) == 5
        # Check sorting (row, then seat)
        assert seats[0].row_number == 1
        assert seats[0].seat_number == 5
        assert seats[-1].row_number == 2
        assert seats[-1].seat_number == 11

    def test_reservation_last_activity_updated(self, test_db, test_seller):
        """Test that reservation last_activity_at is updated."""
        # Create reservation
        vk_user = db.get_or_create_vk_user(12345, "Test User")
        reservation = db.create_reservation(vk_user.id, test_seller.id)

        original_time = reservation.last_activity_at

        # Add seats
        import time
        time.sleep(0.1)  # Small delay to ensure time difference
        db.add_seats_to_reservation(reservation.id, 1, [5], test_seller.id)

        # Get updated reservation
        updated = db.get_active_reservation(vk_user.id)

        assert updated.last_activity_at > original_time


class TestLayoutIntegration:
    """Test layout integration with database."""

    def test_layout_loading(self):
        """Test that layout can be loaded."""
        from bot.utils.layout import load_layout, get_seat_count, is_valid_seat

        layout = load_layout()
        assert "rows" in layout

        # Test row 1 (should have 21 seats according to layout.json)
        assert get_seat_count(1) == 21
        assert is_valid_seat(1, 1) is True
        assert is_valid_seat(1, 21) is True
        assert is_valid_seat(1, 22) is False

        # Test row 10 (should have 28 seats)
        assert get_seat_count(10) == 28
        assert is_valid_seat(10, 28) is True
        assert is_valid_seat(10, 29) is False


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
