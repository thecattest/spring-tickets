#!/usr/bin/env python3
"""
Создание начального администратора.

Использование:
    python scripts/create_admin.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal, init_db
from models.user import AppUser
from models.base import UserRole
from sqlalchemy import select

VK_USER_ID = 498417215
DISPLAY_NAME = "Илья Водопьянов"


def main():
    init_db()

    with SessionLocal() as session:
        stmt = (
            select(AppUser)
            .where(AppUser.vk_user_id == VK_USER_ID)
            .where(AppUser.is_active == True)
        )
        existing = session.execute(stmt).scalar_one_or_none()

        if existing:
            if existing.role == UserRole.ADMIN:
                print(f"Админ уже существует: {existing}")
                return
            existing.role = UserRole.ADMIN
            existing.display_name = DISPLAY_NAME
            session.commit()
            print(f"Обновлён до админа: {existing}")
            return

        user = AppUser(
            vk_user_id=VK_USER_ID,
            role=UserRole.ADMIN,
            display_name=DISPLAY_NAME,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        print(f"Создан админ: {user}")


if __name__ == "__main__":
    main()
