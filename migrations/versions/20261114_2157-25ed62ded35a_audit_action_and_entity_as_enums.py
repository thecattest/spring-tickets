"""audit action and entity as enums

audit_log.action_type и entity_type: свободный TEXT → VARCHAR(32) + CHECK
(AuditAction, AuditEntity в tickets.models.base), как у остальных енамов.

Это сужение (contract), но безопасное вместе с кодом: текущий и прежний код
пишут только эти значения, все записи в базе в них входят. Если в базе
окажется другое значение, миграция упадёт на создании CHECK — так и надо.

Revision ID: 25ed62ded35a
Revises: 5bbc8a839b2e
Create Date: 2026-11-14 21:57:26.748957+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "25ed62ded35a"
down_revision: str | Sequence[str] | None = "5bbc8a839b2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Значения — литералами, не из енамов моделей: миграция не зависит от их
# будущих изменений
ACTIONS = (
    "reservation_created",
    "reservation_cancelled",
    "seats_added",
    "seats_removed",
    "payment_recorded",
    "payments_verified",
    "reserve_added",
    "reserve_removed",
    "debtors_notification_sent",
    "app_user_saved",
    "app_user_deactivated",
)
ENTITIES = ("reservation", "payment", "seat_assignment", "reminder", "app_user")

COLUMNS = {
    # колонка: (имя CHECK, значения, прежний комментарий)
    "action_type": ("ck_audit_log_auditaction", ACTIONS, "Каталог типов действий уточняется позже"),
    "entity_type": (
        "ck_audit_log_auditentity",
        ENTITIES,
        "reservation/payment/expense/seat_assignment/...",
    ),
}


def upgrade() -> None:
    for column, (constraint, values, old_comment) in COLUMNS.items():
        op.alter_column(
            "audit_log",
            column,
            existing_type=sa.Text(),
            type_=sa.String(32),
            comment=None,
            existing_comment=old_comment,
            existing_nullable=False,
        )
        listed = ", ".join(f"'{v}'" for v in values)
        op.create_check_constraint(op.f(constraint), "audit_log", f"{column} IN ({listed})")


def downgrade() -> None:
    for column, (constraint, _, old_comment) in COLUMNS.items():
        op.drop_constraint(op.f(constraint), "audit_log", type_="check")
        op.alter_column(
            "audit_log",
            column,
            existing_type=sa.String(32),
            type_=sa.Text(),
            comment=old_comment,
            existing_nullable=False,
        )
