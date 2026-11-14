"""
Пользователи: покупатели (VkUser — кто пишет билетёрам в VK) и пользователи
системы (AppUser — билетёры и админы).
"""

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tickets.models.base import UserRole
from tickets.models.user import AppUser
from tickets.models.vk_user import VkUser
from tickets.services.errors import NotAllowedError
from tickets.time import utcnow

logger = logging.getLogger(__name__)


# --- покупатели -------------------------------------------------------------


def get_or_create_vk_user(session: Session, vk_id: int, display_name: str) -> VkUser:
    """Покупатель по VK ID; создаётся при первом обращении, имя обновляется."""
    vk_user = session.scalar(select(VkUser).where(VkUser.vk_user_id == vk_id))
    if vk_user:
        if vk_user.display_name != display_name:
            vk_user.display_name = display_name
            vk_user.updated_at = utcnow()
        return vk_user

    vk_user = VkUser(vk_user_id=vk_id, display_name=display_name)
    try:
        # SAVEPOINT: если того же покупателя параллельно создал другой
        # запрос, откатываем только вставку и берём уже созданного
        with session.begin_nested():
            session.add(vk_user)
            session.flush()
    except IntegrityError:
        return session.scalars(select(VkUser).where(VkUser.vk_user_id == vk_id)).one()
    logger.info("Created VK user %s", vk_id)
    return vk_user


# --- пользователи системы ---------------------------------------------------


def _active(vk_user_id: int):
    return select(AppUser).where(AppUser.vk_user_id == vk_user_id, AppUser.is_active.is_(True))


def get_active_app_user(session: Session, vk_user_id: int) -> AppUser | None:
    return session.scalar(_active(vk_user_id))


def require_app_user(session: Session, vk_user_id: int) -> AppUser:
    """Активный пользователь системы или NotAllowedError (не билетёр и не админ)."""
    user = get_active_app_user(session, vk_user_id)
    if user is None:
        raise NotAllowedError(f"No active AppUser for VK ID {vk_user_id}")
    return user


def get_role(session: Session, vk_user_id: int) -> UserRole | None:
    user = get_active_app_user(session, vk_user_id)
    return None if user is None else user.role


def is_admin(session: Session, vk_user_id: int) -> bool:
    return get_role(session, vk_user_id) == UserRole.ADMIN


def admin_vk_ids(session: Session) -> list[int]:
    stmt = select(AppUser.vk_user_id).where(
        AppUser.role == UserRole.ADMIN, AppUser.is_active.is_(True)
    )
    return list(session.scalars(stmt))


def active_users(session: Session) -> list[AppUser]:
    """Все активные пользователи системы, админы первыми."""
    stmt = (
        select(AppUser)
        .where(AppUser.is_active.is_(True))
        .order_by(AppUser.role, AppUser.display_name)
    )
    return list(session.scalars(stmt))


def active_sellers(session: Session) -> list[AppUser]:
    """Активные пользователи с VK ID — кому слать напоминания о должниках."""
    stmt = select(AppUser).where(AppUser.is_active.is_(True), AppUser.vk_user_id.isnot(None))
    return list(session.scalars(stmt))


def add_app_user(session: Session, vk_user_id: int, display_name: str, role: UserRole) -> AppUser:
    """Создать пользователя системы или сменить роль и имя у существующего."""
    user = get_active_app_user(session, vk_user_id)
    if user:
        user.role = role
        user.display_name = display_name
        logger.info("Updated AppUser %s role to %s", user.id, role.value)
        return user
    user = AppUser(vk_user_id=vk_user_id, role=role, display_name=display_name, is_active=True)
    session.add(user)
    session.flush()
    logger.info("Created AppUser %s with role %s", user.id, role.value)
    return user


def deactivate_app_user(session: Session, vk_user_id: int) -> None:
    """Мягкое удаление: is_active = false (история действий сохраняется)."""
    user = get_active_app_user(session, vk_user_id)
    if user:
        user.is_active = False
        logger.info("Deactivated AppUser %s", user.id)
