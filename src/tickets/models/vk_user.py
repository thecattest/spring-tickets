"""
VkUser model - покупатели (VK-аккаунты).
"""

from datetime import datetime

from sqlalchemy import BigInteger, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from tickets.models.base import Base
from tickets.time import utcnow


class VkUser(Base):
    """Покупатели (VK-аккаунты)."""

    __tablename__ = "vk_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vk_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        return f"VkUser(id={self.id!r}, vk_user_id={self.vk_user_id!r}, display_name={self.display_name!r})"
