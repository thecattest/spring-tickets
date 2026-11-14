"""baseline schema

Схема на момент перехода на Alembic — совпадает с тем, что создавал
Base.metadata.create_all(). Существующие базы, созданные create_all() или
scripts/migrate_sqlite_to_postgres.py, не мигрируются, а помечаются:
`alembic stamp 67da311fc2b4`.

Revision ID: 67da311fc2b4
Revises:
Create Date: 2026-11-14 13:17:48.442419+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "67da311fc2b4"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "admin",
                "seller",
                name="userrole",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("vk_user_id", sa.BigInteger(), nullable=True),
        sa.Column("vk_profile_url", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_users")),
    )
    op.create_index("app_users_role_idx", "app_users", ["role"], unique=False)
    op.create_index("app_users_vk_user_id_uniq", "app_users", ["vk_user_id"], unique=True)
    op.create_table(
        "vk_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vk_user_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("profile_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vk_users")),
        sa.UniqueConstraint("vk_user_id", name=op.f("uq_vk_users_vk_user_id")),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "actor_type",
            sa.Enum(
                "user",
                "system",
                name="actortype",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "action_type",
            sa.Text(),
            nullable=False,
            comment="Каталог типов действий уточняется позже",
        ),
        sa.Column(
            "entity_type",
            sa.Text(),
            nullable=False,
            comment="reservation/payment/expense/seat_assignment/...",
        ),
        sa.Column(
            "entity_id", sa.Text(), nullable=True, comment="Строкой (на случай разных типов id)"
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["app_users.id"], name=op.f("fk_audit_log_actor_user_id_app_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("audit_log_action_type_idx", "audit_log", ["action_type"], unique=False)
    op.create_index("audit_log_actor_user_idx", "audit_log", ["actor_user_id"], unique=False)
    op.create_index("audit_log_created_at_idx", "audit_log", ["created_at"], unique=False)
    op.create_index("audit_log_entity_idx", "audit_log", ["entity_type", "entity_id"], unique=False)
    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("buyer_vk_user_id", sa.Integer(), nullable=False),
        sa.Column("sold_by_user_id", sa.Integer(), nullable=False, comment="Кто оформил бронь"),
        sa.Column(
            "state",
            sa.Enum(
                "active",
                "cancelled",
                name="reservationstate",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Для напоминаний: 7 дней после последнего действия",
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["buyer_vk_user_id"],
            ["vk_users.id"],
            name=op.f("fk_reservations_buyer_vk_user_id_vk_users"),
        ),
        sa.ForeignKeyConstraint(
            ["sold_by_user_id"],
            ["app_users.id"],
            name=op.f("fk_reservations_sold_by_user_id_app_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reservations")),
    )
    op.create_index("reservations_buyer_idx", "reservations", ["buyer_vk_user_id"], unique=False)
    op.create_index(
        "reservations_last_activity_idx", "reservations", ["last_activity_at"], unique=False
    )
    op.create_index(
        "reservations_one_active_per_buyer",
        "reservations",
        ["buyer_vk_user_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_index("reservations_sold_by_idx", "reservations", ["sold_by_user_id"], unique=False)
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reservation_id", sa.Integer(), nullable=False),
        sa.Column(
            "recorded_by_user_id", sa.Integer(), nullable=False, comment="Кто отметил оплату"
        ),
        sa.Column("vk_message_url", sa.Text(), nullable=True),
        sa.Column(
            "vk_message_ts", sa.DateTime(timezone=True), nullable=True, comment="Дата отправки чека"
        ),
        sa.Column(
            "payment_amount",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            comment="Сумма оплаты (руб.)",
        ),
        sa.Column("seat_count", sa.Integer(), nullable=False, comment="Количество оплаченных мест"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "receipt_attachments",
            sa.Text(),
            nullable=True,
            comment="VK media IDs чеков через запятую (photo-123_456,doc-789_012)",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["app_users.id"],
            name=op.f("fk_payments_recorded_by_user_id_app_users"),
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.id"],
            name=op.f("fk_payments_reservation_id_reservations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index("payments_reservation_idx", "payments", ["reservation_id"], unique=False)
    op.create_index("payments_vk_message_ts_idx", "payments", ["vk_message_ts"], unique=False)
    op.create_table(
        "seat_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("seat_number", sa.Integer(), nullable=False),
        # autogenerate не видит CHECK-ограничения — добавлены вручную по модели
        sa.CheckConstraint(
            "row_number BETWEEN 1 AND 24", name=op.f("ck_seat_assignments_row_number_range")
        ),
        sa.CheckConstraint(
            "seat_number BETWEEN 1 AND 28", name=op.f("ck_seat_assignments_seat_number_range")
        ),
        sa.Column(
            "status",
            sa.Enum(
                "booked",
                "paid",
                "reserved",
                name="seatstatus",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("reservation_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["app_users.id"],
            name=op.f("fk_seat_assignments_created_by_user_id_app_users"),
        ),
        sa.ForeignKeyConstraint(
            ["released_by_user_id"],
            ["app_users.id"],
            name=op.f("fk_seat_assignments_released_by_user_id_app_users"),
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.id"],
            name=op.f("fk_seat_assignments_reservation_id_reservations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seat_assignments")),
    )
    op.create_index(
        "seat_assignments_one_active_per_seat",
        "seat_assignments",
        ["row_number", "seat_number"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_index(
        "seat_assignments_reservation_idx",
        "seat_assignments",
        ["reservation_id"],
        unique=False,
        postgresql_where=sa.text("reservation_id IS NOT NULL AND released_at IS NULL"),
    )
    op.create_table(
        "payment_seats",
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("seat_assignment_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name=op.f("fk_payment_seats_payment_id_payments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["seat_assignment_id"],
            ["seat_assignments.id"],
            name=op.f("fk_payment_seats_seat_assignment_id_seat_assignments"),
        ),
        sa.PrimaryKeyConstraint("payment_id", "seat_assignment_id", name=op.f("pk_payment_seats")),
    )
    op.create_index(
        "payment_seats_one_payment_per_seat", "payment_seats", ["seat_assignment_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("payment_seats_one_payment_per_seat", table_name="payment_seats")
    op.drop_table("payment_seats")
    op.drop_index(
        "seat_assignments_reservation_idx",
        table_name="seat_assignments",
        postgresql_where=sa.text("reservation_id IS NOT NULL AND released_at IS NULL"),
    )
    op.drop_index(
        "seat_assignments_one_active_per_seat",
        table_name="seat_assignments",
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.drop_table("seat_assignments")
    op.drop_index("payments_vk_message_ts_idx", table_name="payments")
    op.drop_index("payments_reservation_idx", table_name="payments")
    op.drop_table("payments")
    op.drop_index("reservations_sold_by_idx", table_name="reservations")
    op.drop_index(
        "reservations_one_active_per_buyer",
        table_name="reservations",
        postgresql_where=sa.text("state = 'active'"),
    )
    op.drop_index("reservations_last_activity_idx", table_name="reservations")
    op.drop_index("reservations_buyer_idx", table_name="reservations")
    op.drop_table("reservations")
    op.drop_index("audit_log_entity_idx", table_name="audit_log")
    op.drop_index("audit_log_created_at_idx", table_name="audit_log")
    op.drop_index("audit_log_actor_user_idx", table_name="audit_log")
    op.drop_index("audit_log_action_type_idx", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("vk_users")
    op.drop_index("app_users_vk_user_id_uniq", table_name="app_users")
    op.drop_index("app_users_role_idx", table_name="app_users")
    op.drop_table("app_users")
