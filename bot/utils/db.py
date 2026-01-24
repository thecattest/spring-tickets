"""
Database operations for the VK bot.

Provides high-level functions for:
- VK user management
- Reservation creation and retrieval
- Seat availability checking
- Seat assignment to reservations
- Audit logging
"""

import logging
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
from models.vk_user import VkUser
from models.user import AppUser
from models.reservation import Reservation
from models.seat_assignment import SeatAssignment
from models.audit import AuditLog
from models.base import SeatStatus, ReservationState, ActorType

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base exception for database operations."""
    pass


class SeatOccupiedError(DatabaseError):
    """Exception raised when trying to assign an occupied seat."""

    def __init__(self, row: int, seat: int, assignment: SeatAssignment):
        self.row = row
        self.seat = seat
        self.assignment = assignment
        super().__init__(f"Seat {row}/{seat} is already occupied")


def get_or_create_vk_user(vk_id: int, display_name: str) -> VkUser:
    """
    Get existing VK user or create new one.

    Args:
        vk_id: VK user ID
        display_name: Display name from VK

    Returns:
        VkUser instance

    Raises:
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            # Try to find existing user
            stmt = select(VkUser).where(VkUser.vk_user_id == vk_id)
            vk_user = session.execute(stmt).scalar_one_or_none()

            if vk_user:
                # Update display name if changed
                if vk_user.display_name != display_name:
                    vk_user.display_name = display_name
                    vk_user.updated_at = datetime.utcnow()
                    session.commit()
                    logger.info(f"Updated VK user {vk_id}: {display_name}")
                return vk_user

            # Create new user
            vk_user = VkUser(
                vk_user_id=vk_id,
                display_name=display_name,
            )
            session.add(vk_user)
            session.commit()
            session.refresh(vk_user)

            logger.info(f"Created VK user {vk_id}: {display_name}")
            return vk_user

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to get/create VK user {vk_id}: {e}")
            raise DatabaseError(f"Failed to get/create VK user: {e}")


def get_active_reservation(vk_user_id: int) -> Optional[Reservation]:
    """
    Get active reservation for VK user (by internal ID).

    Args:
        vk_user_id: VkUser.id (NOT vk_user_id!)

    Returns:
        Active Reservation or None

    Raises:
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            stmt = (
                select(Reservation)
                .where(Reservation.buyer_vk_user_id == vk_user_id)
                .where(Reservation.state == ReservationState.ACTIVE)
            )
            reservation = session.execute(stmt).scalar_one_or_none()
            return reservation

        except Exception as e:
            logger.error(f"Failed to get active reservation for VK user {vk_user_id}: {e}")
            raise DatabaseError(f"Failed to get active reservation: {e}")


def create_reservation(buyer_vk_user_id: int, sold_by_user_id: int) -> Reservation:
    """
    Create new reservation.

    Args:
        buyer_vk_user_id: VkUser.id (NOT vk_user_id!)
        sold_by_user_id: AppUser.id of the seller

    Returns:
        Created Reservation

    Raises:
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            reservation = Reservation(
                buyer_vk_user_id=buyer_vk_user_id,
                sold_by_user_id=sold_by_user_id,
                state=ReservationState.ACTIVE,
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)

            # Audit log
            audit = AuditLog(
                actor_type=ActorType.USER,
                actor_user_id=sold_by_user_id,
                action_type="reservation_created",
                entity_type="reservation",
                entity_id=str(reservation.id),
                payload={
                    "buyer_vk_user_id": buyer_vk_user_id,
                    "sold_by_user_id": sold_by_user_id,
                }
            )
            session.add(audit)
            session.commit()

            logger.info(f"Created reservation {reservation.id} for VK user {buyer_vk_user_id}")
            return reservation

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create reservation: {e}")
            raise DatabaseError(f"Failed to create reservation: {e}")


def is_seat_available(row: int, seat: int) -> bool:
    """
    Check if seat is available (not occupied).

    Args:
        row: Row number
        seat: Seat number

    Returns:
        True if available, False if occupied

    Raises:
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            stmt = (
                select(SeatAssignment)
                .where(SeatAssignment.row_number == row)
                .where(SeatAssignment.seat_number == seat)
                .where(SeatAssignment.released_at.is_(None))
            )
            assignment = session.execute(stmt).scalar_one_or_none()
            return assignment is None

        except Exception as e:
            logger.error(f"Failed to check seat availability {row}/{seat}: {e}")
            raise DatabaseError(f"Failed to check seat availability: {e}")


def get_seat_assignment(row: int, seat: int) -> Optional[SeatAssignment]:
    """
    Get current seat assignment if exists.

    Args:
        row: Row number
        seat: Seat number

    Returns:
        SeatAssignment if occupied, None if available
    """
    with SessionLocal() as session:
        try:
            stmt = (
                select(SeatAssignment)
                .where(SeatAssignment.row_number == row)
                .where(SeatAssignment.seat_number == seat)
                .where(SeatAssignment.released_at.is_(None))
            )
            assignment = session.execute(stmt).scalar_one_or_none()
            return assignment

        except Exception as e:
            logger.error(f"Failed to get seat assignment {row}/{seat}: {e}")
            raise DatabaseError(f"Failed to get seat assignment: {e}")


def add_seats_to_reservation(
    reservation_id: int,
    row: int,
    seats: List[int],
    user_id: int
) -> List[SeatAssignment]:
    """
    Add seats to reservation (atomic operation).

    All seats must be available or none are added.

    Args:
        reservation_id: Reservation ID
        row: Row number
        seats: List of seat numbers
        user_id: AppUser.id of the person adding seats

    Returns:
        List of created SeatAssignment

    Raises:
        SeatOccupiedError: If any seat is occupied
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            # Check all seats are available first
            occupied = []
            for seat in seats:
                stmt = (
                    select(SeatAssignment)
                    .where(SeatAssignment.row_number == row)
                    .where(SeatAssignment.seat_number == seat)
                    .where(SeatAssignment.released_at.is_(None))
                )
                assignment = session.execute(stmt).scalar_one_or_none()
                if assignment:
                    occupied.append((seat, assignment))

            if occupied:
                # Raise error with first occupied seat
                seat, assignment = occupied[0]
                raise SeatOccupiedError(row, seat, assignment)

            # All seats available - add them
            assignments = []
            for seat in seats:
                assignment = SeatAssignment(
                    row_number=row,
                    seat_number=seat,
                    status=SeatStatus.BOOKED,
                    reservation_id=reservation_id,
                    created_by_user_id=user_id,
                )
                session.add(assignment)
                assignments.append(assignment)

            session.commit()

            # Refresh to get IDs
            for assignment in assignments:
                session.refresh(assignment)

            # Update reservation last_activity_at
            stmt = select(Reservation).where(Reservation.id == reservation_id)
            reservation = session.execute(stmt).scalar_one()
            reservation.last_activity_at = datetime.utcnow()
            session.commit()

            # Audit log
            audit = AuditLog(
                actor_type=ActorType.USER,
                actor_user_id=user_id,
                action_type="seats_added",
                entity_type="reservation",
                entity_id=str(reservation_id),
                payload={
                    "row": row,
                    "seats": seats,
                    "count": len(seats),
                }
            )
            session.add(audit)
            session.commit()

            logger.info(f"Added {len(seats)} seats to reservation {reservation_id}: row {row}, seats {seats}")
            return assignments

        except SeatOccupiedError:
            session.rollback()
            raise
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Integrity error adding seats: {e}")
            raise DatabaseError(f"Integrity error: {e}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add seats to reservation: {e}")
            raise DatabaseError(f"Failed to add seats: {e}")


def get_reservation_seats(reservation_id: int) -> List[SeatAssignment]:
    """
    Get all active seats for a reservation.

    Args:
        reservation_id: Reservation ID

    Returns:
        List of SeatAssignment, sorted by row then seat

    Raises:
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            stmt = (
                select(SeatAssignment)
                .where(SeatAssignment.reservation_id == reservation_id)
                .where(SeatAssignment.released_at.is_(None))
                .order_by(SeatAssignment.row_number, SeatAssignment.seat_number)
            )
            assignments = session.execute(stmt).scalars().all()
            return list(assignments)

        except Exception as e:
            logger.error(f"Failed to get reservation seats {reservation_id}: {e}")
            raise DatabaseError(f"Failed to get reservation seats: {e}")


def get_default_seller_id() -> int:
    """
    Get default seller ID (first active seller or admin).

    This is a temporary solution for Phase 1.
    In Phase 2+, we'll identify seller by VK ID.

    Returns:
        AppUser.id

    Raises:
        DatabaseError: If no users exist
    """
    with SessionLocal() as session:
        try:
            stmt = (
                select(AppUser)
                .where(AppUser.is_active == True)
                .order_by(AppUser.id)
            )
            user = session.execute(stmt).scalar_one_or_none()

            if not user:
                raise DatabaseError("No active users found in database")

            return user.id

        except Exception as e:
            logger.error(f"Failed to get default seller: {e}")
            raise DatabaseError(f"Failed to get default seller: {e}")
