"""
Expense model - расходы (админ).
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base


class Expense(Base):
    """Расходы (админ)."""
    
    __tablename__ = "expenses"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("app_users.id"),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    
    # Когда расход фактически произошел (день/время перевода денег),
    # может отличаться от created_at (когда админ внес запись в систему)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    amount_rub: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("amount_rub > 0"),
        nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        # Для сортировки/фильтра по дате расхода в фин.отчете
        Index("expenses_occurred_at_idx", "occurred_at"),
    )
    
    def __repr__(self) -> str:
        return f"Expense(id={self.id!r}, amount_rub={self.amount_rub!r}, occurred_at={self.occurred_at!r})"
