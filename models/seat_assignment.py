"""
SeatAssignment model - единая таблица занятости мест (бронь/оплачено/резерв).
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, SeatStatus


class SeatAssignment(Base):
    """
    Единая таблица занятости мест.

    - Резерв: status='reserved', reservation_id IS NULL
    - Бронь: status IN ('booked', 'paid'), reservation_id заполнен
    - Свободно: отсутствие активной строки (released_at IS NOT NULL или записи нет)
    """

    __tablename__ = "seat_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Координаты места (валидируются дополнительно по JSON layout)
    row_number: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("row_number BETWEEN 1 AND 24"),
        nullable=False
    )
    seat_number: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("seat_number BETWEEN 1 AND 28"),
        nullable=False
    )

    # reserved используется для резерва; booked/paid — для брони
    status: Mapped[SeatStatus] = mapped_column(nullable=False)

    # Если место относится к брони, заполняется reservation_id
    reservation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("reservations.id", ondelete="CASCADE"),
        nullable=True
    )

    # Кто и когда сделал занятие/снятие
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("app_users.id"),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    released_at: Mapped[datetime | None] = mapped_column(nullable=True)
    released_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("app_users.id"),
        nullable=True
    )

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Гарантирует: ровно одно активное назначение на место (в бронь/в резерв) в любой момент времени
        # SQLite поддерживает partial indexes
        Index(
            "seat_assignments_one_active_per_seat",
            "row_number",
            "seat_number",
            unique=True,
            sqlite_where=text("released_at IS NULL"),
        ),
        # Ускоряет: "места этой брони" (день концерта, просмотр брони, отчеты)
        Index(
            "seat_assignments_reservation_idx",
            "reservation_id",
            sqlite_where=text("reservation_id IS NOT NULL AND released_at IS NULL"),
        ),
        # Ускоряет: поиск по месту (ряд/место), например на странице дня концерта
        Index(
            "seat_assignments_row_seat_idx",
            "row_number",
            "seat_number",
            sqlite_where=text("released_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"SeatAssignment(id={self.id!r}, row={self.row_number}, seat={self.seat_number}, "
            f"status={self.status!r}, reservation_id={self.reservation_id})"
        )
