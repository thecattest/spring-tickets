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
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
from models.vk_user import VkUser
from models.user import AppUser
from models.reservation import Reservation
from models.seat_assignment import SeatAssignment
from models.payment import Payment, PaymentSeat
from models.audit import AuditLog
from models.base import SeatStatus, ReservationState, ActorType, UserRole
from bot.config import SEAT_PRICE

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base exception for database operations."""
    pass


class PermissionError(DatabaseError):
    """Exception raised when user lacks permission for operation."""
    pass


class SeatOccupiedError(DatabaseError):
    """Exception raised when trying to assign an occupied seat."""

    def __init__(self, row: int, seat: int, assignment: SeatAssignment):
        self.row = row
        self.seat = seat
        self.assignment = assignment
        super().__init__(f"Seat {row}/{seat} is already occupied")


class InsufficientSeatsError(DatabaseError):
    """Exception raised when requested payment count exceeds available BOOKED seats."""

    def __init__(self, requested: int, available: int):
        self.requested = requested
        self.available = available
        super().__init__(f"Requested {requested} seats but only {available} BOOKED seats available")


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
                .limit(1)
            )
            user = session.execute(stmt).scalar_one_or_none()

            if not user:
                raise DatabaseError("No active users found in database")

            return user.id

        except Exception as e:
            logger.error(f"Failed to get default seller: {e}")
            raise DatabaseError(f"Failed to get default seller: {e}")


def is_user_admin(vk_user_id: int) -> bool:
    """
    Check if VK user is an admin.

    Args:
        vk_user_id: VK user ID of the seller

    Returns:
        True if user is admin, False otherwise
    """
    with SessionLocal() as session:
        stmt = (
            select(AppUser)
            .where(AppUser.vk_user_id == vk_user_id)
            .where(AppUser.is_active == True)
        )
        user = session.execute(stmt).scalar_one_or_none()
        return user is not None and user.role == UserRole.ADMIN


def get_reservation_with_seats(reservation_id: int) -> tuple[Optional[Reservation], List[SeatAssignment]]:
    """
    Get reservation and its active seats.

    Args:
        reservation_id: Reservation ID

    Returns:
        Tuple of (Reservation or None, List of SeatAssignment)

    Raises:
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            # Get reservation
            stmt = select(Reservation).where(Reservation.id == reservation_id)
            reservation = session.execute(stmt).scalar_one_or_none()

            # Get active seats
            seats_stmt = (
                select(SeatAssignment)
                .where(SeatAssignment.reservation_id == reservation_id)
                .where(SeatAssignment.released_at.is_(None))
                .order_by(SeatAssignment.row_number, SeatAssignment.seat_number)
            )
            seats = session.execute(seats_stmt).scalars().all()

            return reservation, list(seats)

        except Exception as e:
            logger.error(f"Failed to get reservation with seats {reservation_id}: {e}")
            raise DatabaseError(f"Failed to get reservation with seats: {e}")


def release_seats(
    reservation_id: int,
    row: int,
    seats: List[int],
    user_id: int
) -> int:
    """
    Release seats from reservation (atomic operation).

    Sets released_at = NOW() for specified seats.
    Only releases seats that are BOOKED (not PAID).

    Args:
        reservation_id: Reservation ID
        row: Row number
        seats: List of seat numbers to release
        user_id: AppUser.id performing the action

    Returns:
        Count of released seats

    Raises:
        DatabaseError: If operation fails or seats not found
    """
    with SessionLocal() as session:
        try:
            # Get all matching seat assignments that are BOOKED
            stmt = (
                select(SeatAssignment)
                .where(SeatAssignment.reservation_id == reservation_id)
                .where(SeatAssignment.row_number == row)
                .where(SeatAssignment.seat_number.in_(seats))
                .where(SeatAssignment.released_at.is_(None))
                .where(SeatAssignment.status == SeatStatus.BOOKED)
            )
            assignments = session.execute(stmt).scalars().all()

            if len(assignments) < len(seats):
                # Some seats were not BOOKED or don't exist
                found_seats = {a.seat_number for a in assignments}
                missing = set(seats) - found_seats
                raise DatabaseError(
                    f"Cannot release seats: {missing} are either not found, already released, or are PAID"
                )

            # Release all seats
            now = datetime.utcnow()
            for assignment in assignments:
                assignment.released_at = now

            # Update reservation last_activity_at
            reservation_stmt = select(Reservation).where(Reservation.id == reservation_id)
            reservation = session.execute(reservation_stmt).scalar_one()
            reservation.last_activity_at = now

            session.commit()

            # Audit log
            audit = AuditLog(
                actor_type=ActorType.USER,
                actor_user_id=user_id,
                action_type="seats_removed",
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

            logger.info(f"Released {len(assignments)} seats from reservation {reservation_id}: row {row}, seats {seats}")
            return len(assignments)

        except DatabaseError:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to release seats: {e}")
            raise DatabaseError(f"Failed to release seats: {e}")


def cancel_reservation(
    reservation_id: int,
    user_id: int,
    is_admin: bool
) -> bool:
    """
    Cancel reservation and release all seats.

    Args:
        reservation_id: Reservation ID
        user_id: AppUser.id performing the action
        is_admin: Whether user is admin (can cancel with PAID seats)

    Returns:
        True if cancelled

    Raises:
        PermissionError: If has PAID seats and not admin
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            # Get reservation
            reservation_stmt = select(Reservation).where(Reservation.id == reservation_id)
            reservation = session.execute(reservation_stmt).scalar_one_or_none()

            if not reservation:
                raise DatabaseError(f"Reservation {reservation_id} not found")

            # Get all active seats
            seats_stmt = (
                select(SeatAssignment)
                .where(SeatAssignment.reservation_id == reservation_id)
                .where(SeatAssignment.released_at.is_(None))
            )
            seats = session.execute(seats_stmt).scalars().all()

            # Check for PAID seats
            paid_seats = [s for s in seats if s.status == SeatStatus.PAID]

            if paid_seats and not is_admin:
                raise PermissionError(
                    f"Cannot cancel reservation with {len(paid_seats)} PAID seats. Admin permission required."
                )

            # Release all seats
            now = datetime.utcnow()
            for seat in seats:
                seat.released_at = now

            # Update reservation state
            reservation.state = ReservationState.CANCELLED
            reservation.last_activity_at = now

            session.commit()

            # Audit log
            audit = AuditLog(
                actor_type=ActorType.USER,
                actor_user_id=user_id,
                action_type="reservation_cancelled",
                entity_type="reservation",
                entity_id=str(reservation_id),
                payload={
                    "total_seats": len(seats),
                    "paid_seats": len(paid_seats),
                    "is_admin": is_admin,
                }
            )
            session.add(audit)
            session.commit()

            logger.info(f"Cancelled reservation {reservation_id}: {len(seats)} seats released (paid: {len(paid_seats)})")
            return True

        except (PermissionError, DatabaseError):
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to cancel reservation: {e}")
            raise DatabaseError(f"Failed to cancel reservation: {e}")


def record_payment(
    reservation_id: int,
    seat_count: int,
    user_id: int,
    vk_message_url: Optional[str] = None,
    vk_message_ts: Optional[datetime] = None,
) -> tuple[Payment, List[SeatAssignment]]:
    """
    Record payment for N seats in a reservation (atomic operation).

    Deterministically selects the first seat_count BOOKED seats (row ASC, seat ASC),
    marks them as PAID, creates Payment and PaymentSeat records, and logs audit.

    Args:
        reservation_id: Reservation ID
        seat_count: Number of seats to mark as paid
        user_id: AppUser.id of the person recording payment
        vk_message_url: VK receipt message URL (optional, None for button-flow)
        vk_message_ts: VK receipt message timestamp (optional, None for button-flow)

    Returns:
        Tuple of (Payment, List of SeatAssignment that were marked PAID)

    Raises:
        InsufficientSeatsError: If seat_count > available BOOKED seats
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            # Query BOOKED seats for this reservation, ordered deterministically
            stmt = (
                select(SeatAssignment)
                .where(SeatAssignment.reservation_id == reservation_id)
                .where(SeatAssignment.status == SeatStatus.BOOKED)
                .where(SeatAssignment.released_at.is_(None))
                .order_by(SeatAssignment.row_number.asc(), SeatAssignment.seat_number.asc())
            )
            booked_seats = list(session.execute(stmt).scalars().all())

            if len(booked_seats) < seat_count:
                raise InsufficientSeatsError(seat_count, len(booked_seats))

            # Take first seat_count seats (deterministic)
            selected_seats = booked_seats[:seat_count]
            remaining_booked = booked_seats[seat_count:]

            # Calculate payment amount
            payment_amount = Decimal(seat_count) * Decimal(SEAT_PRICE)

            # Create Payment record
            payment = Payment(
                reservation_id=reservation_id,
                recorded_by_user_id=user_id,
                vk_message_url=vk_message_url,
                vk_message_ts=vk_message_ts,
                payment_amount=payment_amount,
                seat_count=seat_count,
            )
            session.add(payment)
            session.flush()  # get payment.id before creating PaymentSeat

            # Update seats to PAID and create PaymentSeat records
            for seat in selected_seats:
                seat.status = SeatStatus.PAID
                payment_seat = PaymentSeat(
                    payment_id=payment.id,
                    seat_assignment_id=seat.id,
                )
                session.add(payment_seat)

            # Update reservation last_activity_at
            reservation_stmt = select(Reservation).where(Reservation.id == reservation_id)
            reservation = session.execute(reservation_stmt).scalar_one()
            reservation.last_activity_at = datetime.utcnow()

            # Audit log
            audit = AuditLog(
                actor_type=ActorType.USER,
                actor_user_id=user_id,
                action_type="payment_recorded",
                entity_type="payment",
                entity_id=str(payment.id),
                payload={
                    "reservation_id": reservation_id,
                    "seat_count": seat_count,
                    "payment_amount": float(payment_amount),
                    "seat_ids": [seat.id for seat in selected_seats],
                    "partial": len(remaining_booked) > 0,
                }
            )
            session.add(audit)
            session.commit()

            logger.info(
                f"Recorded payment {payment.id} for reservation {reservation_id}: "
                f"{seat_count} seats, {payment_amount} rub, partial={len(remaining_booked) > 0}"
            )
            return payment, selected_seats

        except InsufficientSeatsError:
            session.rollback()
            raise
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Integrity error recording payment: {e}")
            raise DatabaseError(f"Integrity error: {e}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to record payment: {e}")
            raise DatabaseError(f"Failed to record payment: {e}")


def get_app_user_by_vk_id(vk_user_id: int) -> Optional[AppUser]:
    """
    Get AppUser by VK user ID.

    Used to resolve the admin's AppUser.id from their VK user ID so that
    created_by_user_id on SeatAssignment is the internal AppUser.id (NOT the VK user ID).

    Args:
        vk_user_id: VK user ID of the admin/seller

    Returns:
        AppUser if found and active, None otherwise

    Raises:
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            stmt = (
                select(AppUser)
                .where(AppUser.vk_user_id == vk_user_id)
                .where(AppUser.is_active == True)
            )
            user = session.execute(stmt).scalar_one_or_none()
            return user

        except Exception as e:
            logger.error(f"Failed to get AppUser by VK user ID {vk_user_id}: {e}")
            raise DatabaseError(f"Failed to get AppUser by VK user ID: {e}")


def add_reserve(row: int, seats: List[int], comment: str, user_id: int) -> List[SeatAssignment]:
    """
    Add reserved seats (atomic operation, admin-only).

    Creates SeatAssignment rows with status=RESERVED and reservation_id=None.
    All seats must be available or none are added.

    Args:
        row: Row number
        seats: List of seat numbers to reserve
        comment: Reserve reason/note (stored in SeatAssignment.note)
        user_id: AppUser.id of the admin performing the action

    Returns:
        List of created SeatAssignment

    Raises:
        SeatOccupiedError: If any seat is already occupied
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            # Check all seats are available first (atomic — check before any insert)
            for seat in seats:
                stmt = (
                    select(SeatAssignment)
                    .where(SeatAssignment.row_number == row)
                    .where(SeatAssignment.seat_number == seat)
                    .where(SeatAssignment.released_at.is_(None))
                )
                assignment = session.execute(stmt).scalar_one_or_none()
                if assignment:
                    raise SeatOccupiedError(row, seat, assignment)

            # All seats available — create RESERVED assignments
            assignments = []
            for seat in seats:
                assignment = SeatAssignment(
                    row_number=row,
                    seat_number=seat,
                    status=SeatStatus.RESERVED,
                    reservation_id=None,
                    created_by_user_id=user_id,
                    note=comment,
                )
                session.add(assignment)
                assignments.append(assignment)

            session.commit()

            # Refresh to get IDs
            for assignment in assignments:
                session.refresh(assignment)

            # Audit log
            audit = AuditLog(
                actor_type=ActorType.USER,
                actor_user_id=user_id,
                action_type="reserve_added",
                entity_type="seat_assignment",
                payload={
                    "row": row,
                    "seats": seats,
                    "comment": comment,
                    "user_id": user_id,
                    "count": len(seats),
                }
            )
            session.add(audit)
            session.commit()

            logger.info(f"Added reserve: row {row}, seats {seats}, comment={comment!r}, user_id={user_id}")
            return assignments

        except SeatOccupiedError:
            session.rollback()
            raise
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Integrity error adding reserve: {e}")
            raise DatabaseError(f"Integrity error: {e}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add reserve: {e}")
            raise DatabaseError(f"Failed to add reserve: {e}")


def release_reserve(row: int, seats: List[int], user_id: int) -> List[dict]:
    """
    Release reserved seats (atomic operation, admin-only).

    Sets released_at on RESERVED seats and returns previous notes for audit.

    Args:
        row: Row number
        seats: List of seat numbers to release
        user_id: AppUser.id of the admin performing the action

    Returns:
        List of dicts with previous notes: [{"seat": seat_number, "note": note}, ...]

    Raises:
        DatabaseError: If any seats are not found as active RESERVED seats,
                       or if operation fails
    """
    with SessionLocal() as session:
        try:
            # Query all matching RESERVED seats
            stmt = (
                select(SeatAssignment)
                .where(SeatAssignment.row_number == row)
                .where(SeatAssignment.seat_number.in_(seats))
                .where(SeatAssignment.status == SeatStatus.RESERVED)
                .where(SeatAssignment.released_at.is_(None))
            )
            assignments = list(session.execute(stmt).scalars().all())

            if len(assignments) < len(seats):
                found_seats = {a.seat_number for a in assignments}
                missing = sorted(set(seats) - found_seats)
                raise DatabaseError(
                    f"Seats not found as active RESERVED in row {row}: {missing}"
                )

            # Collect previous notes before modification
            previous_notes = [
                {"seat": a.seat_number, "note": a.note}
                for a in assignments
            ]

            # Release all seats
            now = datetime.utcnow()
            for assignment in assignments:
                assignment.released_at = now
                assignment.released_by_user_id = user_id

            session.commit()

            # Audit log
            audit = AuditLog(
                actor_type=ActorType.USER,
                actor_user_id=user_id,
                action_type="reserve_removed",
                entity_type="seat_assignment",
                payload={
                    "row": row,
                    "seats": seats,
                    "previous_notes": previous_notes,
                    "user_id": user_id,
                }
            )
            session.add(audit)
            session.commit()

            logger.info(f"Released reserve: row {row}, seats {seats}, user_id={user_id}")
            return previous_notes

        except DatabaseError:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to release reserve: {e}")
            raise DatabaseError(f"Failed to release reserve: {e}")


def get_debtors(seller_id: Optional[int] = None) -> List[dict]:
    """
    Get list of debtors: reservations with BOOKED seats and no activity for 7+ days.

    A debtor is a reservation that:
    - Is ACTIVE state
    - Has last_activity_at <= (now - 7 days)
    - Has at least one unreleased BOOKED seat (released_at IS NULL, status=BOOKED)

    Args:
        seller_id: If provided, filter to reservations by this seller (AppUser.id).
                   If None, returns all debtors across all sellers (admin view).

    Returns:
        List of dicts: {
            'reservation_id': int,
            'buyer_display_name': str,
            'booked_seat_count': int,
            'debt_amount': Decimal,
            'days_since_activity': int,
            'last_activity_at': datetime,
        }
        Sorted by last_activity_at ASC (oldest first).

    Raises:
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            threshold = datetime.utcnow() - timedelta(days=7)

            # Correlated subquery: count BOOKED unreleased seats per reservation
            booked_count_subq = (
                select(func.count(SeatAssignment.id))
                .where(SeatAssignment.reservation_id == Reservation.id)
                .where(SeatAssignment.released_at.is_(None))
                .where(SeatAssignment.status == SeatStatus.BOOKED)
                .scalar_subquery()
            )

            # Main query: active reservations older than threshold with booked seats
            stmt = (
                select(Reservation, VkUser, booked_count_subq.label("booked_count"))
                .join(VkUser, Reservation.buyer_vk_user_id == VkUser.id)
                .where(Reservation.state == ReservationState.ACTIVE)
                .where(Reservation.last_activity_at <= threshold)
                .where(booked_count_subq > 0)
                .order_by(Reservation.last_activity_at.asc())
            )

            if seller_id is not None:
                stmt = stmt.where(Reservation.sold_by_user_id == seller_id)

            rows = session.execute(stmt).all()

            now = datetime.utcnow()
            result = []
            for reservation, vk_user, booked_count in rows:
                days_since = (now - reservation.last_activity_at).days
                debt_amount = Decimal(booked_count) * Decimal(SEAT_PRICE)
                result.append({
                    'reservation_id': reservation.id,
                    'buyer_display_name': vk_user.display_name,
                    'booked_seat_count': booked_count,
                    'debt_amount': debt_amount,
                    'days_since_activity': days_since,
                    'last_activity_at': reservation.last_activity_at,
                })

            logger.info(
                f"get_debtors(seller_id={seller_id}): found {len(result)} debtors"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to get debtors: {e}")
            raise DatabaseError(f"Failed to get debtors: {e}")


def get_all_active_sellers() -> List[AppUser]:
    """
    Get all active sellers (AppUsers with vk_user_id set).

    Used by the cron reminder script to enumerate sellers who should receive
    debtor reminders. Returns AppUser objects so the cron can call
    get_debtors(seller_id=user.id) for each.

    Returns:
        List of AppUser objects where is_active=True and vk_user_id IS NOT NULL

    Raises:
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            stmt = (
                select(AppUser)
                .where(AppUser.is_active == True)
                .where(AppUser.vk_user_id.isnot(None))
            )
            users = list(session.execute(stmt).scalars().all())
            logger.info(f"get_all_active_sellers(): found {len(users)} active sellers")
            return users

        except Exception as e:
            logger.error(f"Failed to get active sellers: {e}")
            raise DatabaseError(f"Failed to get active sellers: {e}")
