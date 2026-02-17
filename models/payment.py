"""
Payment и PaymentSeat models - оплаты (чеки) и привязка мест к чекам.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base


class Payment(Base):
    """
    Оплаты (чеки).
    
    Билетер указывает какие именно места оплачены этим чеком через таблицу payment_seats.
    """
    
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reservation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("reservations.id"),
        nullable=False
    )
    recorded_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("app_users.id"),
        nullable=False,
        comment="Кто отметил оплату"
    )
    
    vk_message_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vk_message_ts: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Дата отправки чека"
    )

    payment_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Сумма оплаты (руб.)"
    )
    seat_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Количество оплаченных мест"
    )

    recorded_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        # Для просмотра оплат по конкретной брони
        Index("payments_reservation_idx", "reservation_id"),
        # Для фин.отчетов/сортировки по дате чека
        Index("payments_vk_message_ts_idx", "vk_message_ts"),
    )
    
    def __repr__(self) -> str:
        return f"Payment(id={self.id!r}, reservation_id={self.reservation_id!r}, vk_message_ts={self.vk_message_ts!r})"


class PaymentSeat(Base):
    """
    Связь оплат с конкретными местами.
    
    Билетер отмечает, какие места оплачены данным чеком.
    """
    
    __tablename__ = "payment_seats"
    
    payment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("payments.id", ondelete="CASCADE"),
        primary_key=True
    )
    seat_assignment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("seat_assignments.id"),
        primary_key=True
    )
    
    __table_args__ = (
        # Гарантия: одно активное место не может быть "оплачено" двумя разными чеками
        Index("payment_seats_one_payment_per_seat", "seat_assignment_id", unique=True),
    )
    
    def __repr__(self) -> str:
        return f"PaymentSeat(payment_id={self.payment_id!r}, seat_assignment_id={self.seat_assignment_id!r})"
