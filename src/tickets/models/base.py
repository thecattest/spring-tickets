"""
Base declarative class and ENUM types for SQLAlchemy ORM models.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, MetaData
from sqlalchemy.orm import DeclarativeBase

# Предсказуемые имена ограничений и индексов — нужны Alembic, чтобы находить
# и менять их миграциями (иначе имена выбирает Postgres).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {
        # Любая колонка Mapped[datetime] — timestamptz (момент времени, хранится в UTC)
        datetime: DateTime(timezone=True),
        # Любая колонка Mapped[<Enum>] — VARCHAR + CHECK, а не нативный ENUM Postgres:
        # новые значения добавляются обычной миграцией CHECK, а не ALTER TYPE.
        # В БД хранятся значения ('paid'), а не имена членов ('PAID').
        enum.Enum: Enum(
            enum.Enum,
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=lambda e: [member.value for member in e],
        ),
    }


# ENUM types


class UserRole(str, enum.Enum):
    """Роли пользователей системы (админ/билетер)."""

    ADMIN = "admin"
    SELLER = "seller"


class ReservationState(str, enum.Enum):
    """Состояние брони."""

    ACTIVE = "active"
    CANCELLED = "cancelled"


class SeatStatus(str, enum.Enum):
    """Статус места (бронь/оплачено/резерв)."""

    BOOKED = "booked"  # забронировано (не оплачено)
    PAID = "paid"  # оплачено
    RESERVED = "reserved"  # резерв под гостей


class ActorType(str, enum.Enum):
    """Тип актора в аудит-логе."""

    USER = "user"  # билетёр или админ в боте (actor_user_id — AppUser.id)
    SYSTEM = "system"  # фоновые задачи
    WEB_ADMIN = "web_admin"  # вход на /payments по паролю (учёток в вебе нет; IP — в payload)


class AuditAction(str, enum.Enum):
    """
    Тип действия в audit_log.action_type. Новое значение — миграция,
    расширяющая CHECK (страж tests/test_migrations.py напомнит).
    """

    RESERVATION_CREATED = "reservation_created"
    RESERVATION_CANCELLED = "reservation_cancelled"
    SEATS_ADDED = "seats_added"
    SEATS_REMOVED = "seats_removed"
    PAYMENT_RECORDED = "payment_recorded"
    PAYMENTS_VERIFIED = "payments_verified"
    RESERVE_ADDED = "reserve_added"
    RESERVE_REMOVED = "reserve_removed"
    DEBTORS_NOTIFICATION_SENT = "debtors_notification_sent"
    APP_USER_SAVED = "app_user_saved"
    APP_USER_DEACTIVATED = "app_user_deactivated"


class AuditEntity(str, enum.Enum):
    """С какой сущностью действие (audit_log.entity_type; id — в entity_id)."""

    RESERVATION = "reservation"
    PAYMENT = "payment"
    SEAT_ASSIGNMENT = "seat_assignment"  # резервы
    REMINDER = "reminder"  # напоминание о должниках (без id)
    APP_USER = "app_user"
