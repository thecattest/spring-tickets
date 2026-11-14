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

    USER = "user"
    SYSTEM = "system"
