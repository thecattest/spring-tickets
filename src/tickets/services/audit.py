"""
Аудит: запись о действии в той же транзакции, что и само действие —
либо есть и изменение, и запись о нём, либо ничего.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from tickets.models.audit import AuditLog
from tickets.models.base import ActorType, AuditAction, AuditEntity

# AuditAction и AuditEntity — в tickets.models.base, рядом с остальными енамами;
# здесь доступны и как audit.AuditAction / audit.AuditEntity
__all__ = ["AuditAction", "AuditEntity", "log"]


def log(
    session: AsyncSession,
    action: AuditAction,
    *,
    entity_type: AuditEntity,
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
