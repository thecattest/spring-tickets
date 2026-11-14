"""
Reservation model - брони билетов.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, ReservationState
from timeutils import utcnow


class Reservation(Base):
    """Бронь билетов."""

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buyer_vk_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vk_users.id"), nullable=False
    )
    sold_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("app_users.id"), nullable=False, comment="Кто оформил бронь"
    )

    state: Mapped[ReservationState] = mapped_column(nullable=False, default=ReservationState.ACTIVE)

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=utcnow,
        comment="Для напоминаний: 7 дней после последнего действия",
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        # Частые выборки "бронь покупателя"
        Index("reservations_buyer_idx", "buyer_vk_user_id"),
        # Гарантирует: не больше одной активной брони на покупателя
        Index(
            "reservations_one_active_per_buyer",
            "buyer_vk_user_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
        # Для отчетов и напоминаний "мои продажи/мои должники"
        Index("reservations_sold_by_idx", "sold_by_user_id"),
        # Для выборки должников по последней активности
        Index("reservations_last_activity_idx", "last_activity_at"),
    )

    def __repr__(self) -> str:
        return f"Reservation(id={self.id!r}, buyer_vk_user_id={self.buyer_vk_user_id!r}, state={self.state!r})"
