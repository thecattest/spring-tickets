"""
AppUser model - внутренние пользователи системы (админ/билетер).
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, UserRole
from timeutils import utcnow


class AppUser(Base):
    """Пользователи системы (админ/билетер)."""

    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[UserRole] = mapped_column(nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)

    # Связка с VK (если билетер тоже в VK)
    vk_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    vk_profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)

    __table_args__ = (
        # Ускоряет выборки по роли (например, рассылка напоминаний всем билетерам)
        Index("app_users_role_idx", "role"),
        # Чтобы один vk_user_id не был привязан к нескольким пользователям системы
        # SQLite поддерживает partial indexes
        # UNIQUE в Postgres допускает много NULL — условие не нужно
        Index("app_users_vk_user_id_uniq", "vk_user_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"AppUser(id={self.id!r}, role={self.role!r}, display_name={self.display_name!r})"
