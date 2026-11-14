"""
Контекст диалога билетёра (хранится в Redis вместе с состоянием FSM).

Схема при чтении (ROADMAP → Миграции и совместимость): новые поля — только с
умолчаниями, лишние поля игнорируются; не читается — лог, сброс, «начните
заново» (tickets.bot.fsm.storage). Поле v — версия формата для будущих
несовместимых изменений.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from tickets.bot.fsm.states import BotState


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Client(_Model):
    """Покупатель, с которым сейчас работает билетёр, и его бронь."""

    reservation_id: int
    buyer_id: int  # VkUser.id — id в базе
    buyer_vk_id: int  # id пользователя в VK
    buyer_name: str


class Receipt(_Model):
    """Чек из пересланного сообщения покупателя (ждёт выбора количества мест)."""

    vk_message_ts: datetime | None = None
    # [{'type': 'photo'|'doc', 'url', 'title'}] — для пересылки чека админам
    attachments: list[dict] = []


class PendingSwitch(_Model):
    """На кого билетёр переключится, если ответит «Да»."""

    buyer_id: int
    buyer_vk_id: int
    buyer_name: str
    reservation_id: int | None  # None — брони нет, при переключении создаётся
    receipt: Receipt | None = None  # переключение по чеку — сразу к оплате


class SavedState(_Model):
    """Куда вернуться, если билетёр ответит «Нет» на переключение."""

    state: BotState
    context: Context


class Context(_Model):
    v: int = 1

    client: Client | None = None
    # Сценарий начат из меню брони — «Готово» и «Отмена» возвращают в меню
    from_main_menu: bool = False

    current_row: int | None = None
    seats_to_delete: list[int] = []

    receipt: Receipt | None = None  # оплата: чек, по которому выбирается количество

    pending: PendingSwitch | None = None
    saved: SavedState | None = None

    # Резерв (только админ)
    admin_user_id: int | None = None
    reserve_seats: list[int] = []
    reserve_seats_to_remove: list[int] = []


SavedState.model_rebuild()
