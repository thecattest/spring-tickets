"""audit actor web_admin

Новое значение ActorType.WEB_ADMIN — действия на странице оплат (вход по
паролю, учёток в вебе нет). Expand: CHECK расширяется, старый код с новой
схемой работает — миграция выходит вместе с кодом, который пишет значение.

Revision ID: 5bbc8a839b2e
Revises: 67da311fc2b4
Create Date: 2026-11-14 21:34:56.977591+00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5bbc8a839b2e"
down_revision: str | Sequence[str] | None = "67da311fc2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Значения — литералами, не из ActorType: миграция не зависит от текущих моделей
CONSTRAINT = "ck_audit_log_actortype"


def _set_values(*values: str) -> None:
    listed = ", ".join(f"'{v}'" for v in values)
    op.drop_constraint(op.f(CONSTRAINT), "audit_log", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "audit_log", f"actor_type IN ({listed})")


def upgrade() -> None:
    _set_values("user", "system", "web_admin")


def downgrade() -> None:
    # Упадёт, если в audit_log уже есть web_admin — так и надо: молча терять
    # записи аудита нельзя, их сначала надо перенести или удалить осознанно
    _set_values("user", "system")
