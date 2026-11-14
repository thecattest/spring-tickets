"""
AuditLog model - аудит-лог (полная история действий).
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from tickets.models.base import ActorType, AuditAction, AuditEntity, Base
from tickets.time import utcnow


class AuditLog(Base):
    """Аудит-лог (полная история действий пользователей и системы)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)

    actor_type: Mapped[ActorType] = mapped_column(nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("app_users.id"), nullable=True
    )

    action_type: Mapped[AuditAction] = mapped_column(nullable=False)
    entity_type: Mapped[AuditEntity] = mapped_column(nullable=False)
    entity_id: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Строкой (на случай разных типов id)"
    )

    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        # Быстрая прокрутка/фильтрация по времени
        Index("audit_log_created_at_idx", "created_at"),
        # Фильтр по типу действия
        Index("audit_log_action_type_idx", "action_type"),
        # Фильтр "все события по сущности"
        Index("audit_log_entity_idx", "entity_type", "entity_id"),
        # Фильтр по пользователю (кто делал)
        Index("audit_log_actor_user_idx", "actor_user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"AuditLog(id={self.id!r}, action_type={self.action_type!r}, "
            f"entity_type={self.entity_type!r}, entity_id={self.entity_id!r})"
        )
