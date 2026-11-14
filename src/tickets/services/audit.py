"""
Аудит: запись о действии в той же транзакции, что и само действие —
либо есть и изменение, и запись о нём, либо ничего.
"""

import enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from tickets.models.audit import AuditLog
from tickets.models.base import ActorType


class AuditAction(str, enum.Enum):
    """Типы действий в audit_log.action_type (значения совпадают с прежними строками)."""

    RESERVATION_CREATED = "reservation_created"
    RESERVATION_CANCELLED = "reservation_cancelled"
    SEATS_ADDED = "seats_added"
    SEATS_REMOVED = "seats_removed"
    PAYMENT_RECORDED = "payment_recorded"
    RESERVE_ADDED = "reserve_added"
    RESERVE_REMOVED = "reserve_removed"
    DEBTORS_NOTIFICATION_SENT = "debtors_notification_sent"


def log(
    session: AsyncSession,
    action: AuditAction,
    *,
    entity_type: str,
    entity_id: int | str | None = None,
    actor_user_id: int | None,
    payload: dict[str, Any],
    actor_type: ActorType = ActorType.USER,
) -> AuditLog:
    entry = AuditLog(
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        action_type=action.value,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        payload=payload,
    )
    session.add(entry)
    return entry
