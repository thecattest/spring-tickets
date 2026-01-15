"""
Base declarative class and ENUM types for SQLAlchemy ORM models.
"""

import enum
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ENUM types matching DB_SCHEMA.md

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
    BOOKED = "booked"      # забронировано (не оплачено)
    PAID = "paid"          # оплачено
    RESERVED = "reserved"  # резерв под гостей


class ActorType(str, enum.Enum):
    """Тип актора в аудит-логе."""
    USER = "user"
    SYSTEM = "system"
