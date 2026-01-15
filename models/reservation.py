"""
Reservation model - брони билетов.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base, ReservationState


class Reservation(Base):
    """Бронь билетов."""
    
    __tablename__ = "reservations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buyer_vk_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("vk_users.id"),
        nullable=False
    )
    sold_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("app_users.id"),
        nullable=False,
        comment="Кто оформил бронь"
    )
    
    state: Mapped[ReservationState] = mapped_column(nullable=False, default=ReservationState.ACTIVE)
    
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        comment="Для напоминаний: 7 дней после последнего действия"
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    __table_args__ = (
        # Частые выборки "бронь покупателя"
        Index("reservations_buyer_idx", "buyer_vk_user_id"),
        # Для отчетов и напоминаний "мои продажи/мои должники"
        Index("reservations_sold_by_idx", "sold_by_user_id"),
        # Для выборки должников по последней активности
        Index("reservations_last_activity_idx", "last_activity_at"),
    )
    
    def __repr__(self) -> str:
        return f"Reservation(id={self.id!r}, buyer_vk_user_id={self.buyer_vk_user_id!r}, state={self.state!r})"
