"""
ReconcileCheckpoint model - чекапы финансов (проверено).
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class ReconcileCheckpoint(Base):
    """Чекапы финансов (проверено)."""

    __tablename__ = "reconcile_checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checked_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("app_users.id"),
        nullable=True
    )
    checked_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Быстро найти последний чекап и фильтровать "до/после него"
        Index("reconcile_checkpoints_checked_at_idx", "checked_at"),
    )

    def __repr__(self) -> str:
        return f"ReconcileCheckpoint(id={self.id!r}, checked_at={self.checked_at!r})"
