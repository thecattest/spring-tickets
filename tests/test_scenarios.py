"""
Сценарии бота: события как от Long Poll, VK подменён (scenario.py), Postgres и
Redis настоящие (testcontainers).

Фиксируют текущее поведение перед переписыванием бота (ROADMAP, этап 7):
переписанный бот обязан их пройти. Тексты сверяются по ключевым фрагментам,
данные — по базе. Странности текущего поведения, которые ещё не решено
менять, отмечены «как сейчас».
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from conftest import TEST_OWNER_VK_ID
from tests.scenario import photo
from tickets.bot.utils import db
from tickets.db import SessionLocal
from tickets.models.base import ReservationState, SeatStatus, UserRole
from tickets.models.payment import Payment
from tickets.models.reservation import Reservation
from tickets.models.seat_assignment import SeatAssignment
from tickets.models.user import AppUser

pytestmark = pytest.mark.asyncio

SELLER = 201
ADMIN = 202
STRANGER = 111
BUYER = 301
BUYER2 = 302
NEWBIE = 401
OWNER = TEST_OWNER_VK_ID

MAIN_KEYBOARD = ["Отмена", "Справка", "Должники", "Резерв", "Оплаты", "День концерта"]
RESERVATION_MENU = ["Добавить", "Удалить", "Удалить все", "Оплата"]


@pytest_asyncio.fixture(autouse=True)
async def users(bot):
    await db.add_app_user(SELLER, "Билетёр", UserRole.SELLER)
    await db.add_app_user(ADMIN, "Админ", UserRole.ADMIN)
    bot.vk.users.update(
        {BUYER: ("Иван", "Покупатель"), BUYER2: ("Пётр", "Второй"), NEWBIE: ("Новый", "Билетёр")}
    )


def seats(status: SeatStatus | None = None) -> list[tuple[int, int, str]]:
    """Занятые сейчас места: (ряд, место, статус), по порядку."""
    with SessionLocal() as session:
        stmt = select(SeatAssignment).where(SeatAssignment.released_at.is_(None))
        if status is not None:
            stmt = stmt.where(SeatAssignment.status == status)
        rows = session.scalars(stmt.order_by(SeatAssignment.row_number, SeatAssignment.seat_number))
        return [(s.row_number, s.seat_number, s.status.value) for s in rows]


def reservations() -> list[Reservation]:
    with SessionLocal() as session:
        return list(session.scalars(select(Reservation).order_by(Reservation.id)))


async def book(bot, who: int, buyer: int, row: str, seat_list: str) -> None:
    """Новая бронь: пересылка → ряд → места → «Готово»."""
    await bot.send(who, "", fwd_from=buyer)
    await bot.send(who, row)
    await bot.send(who, seat_list)
    await bot.send(who, "Готово")


# --- доступ ---------------------------------------------------------------


async def test_start_shows_main_keyboard(bot):
    [reply] = await bot.send(STRANGER, "/start")
    assert "Добро пожаловать" in reply.text
    assert reply.buttons == MAIN_KEYBOARD


async def test_stranger_cannot_create_reservation(bot):
    [reply] = await bot.send(STRANGER, "", fwd_from=BUYER)
    assert reply.text == "Вы не зарегистрированы в системе."
    assert reservations() == []


# --- бронь ----------------------------------------------------------------


async def test_new_reservation(bot):
    [r] = await bot.send(SELLER, "", fwd_from=BUYER)
    assert "Создана новая бронь для Иван Покупатель" in r.text
    assert await bot.state(SELLER) == "BotState:awaiting_row"

    [r] = await bot.send(SELLER, "99")
    assert "Неверный ряд" in r.text
    assert await bot.state(SELLER) == "BotState:awaiting_row"

    [r] = await bot.send(SELLER, "5")
    assert r.text.startswith("Ряд 5 (26 мест)")

    [r] = await bot.send(SELLER, "3-5")
    assert "Добавлено 3 места" in r.text
    assert r.buttons == ["Добавить еще", "Готово"]

    [r] = await bot.send(SELLER, "Готово")
    assert "Места забронированы" in r.text
    assert "К оплате: 4500 руб." in r.text  # 3 × SEAT_PRICE 1500
    assert await bot.state(SELLER) is None

    [reservation] = reservations()
    assert reservation.state == ReservationState.ACTIVE
    assert seats() == [(5, 3, "booked"), (5, 4, "booked"), (5, 5, "booked")]


async def test_existing_reservation_opens_menu(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    [r] = await bot.send(SELLER, "", fwd_from=BUYER)
    assert r.text.startswith("Бронь #1 — Иван Покупатель")
    assert "📌Бронь: 3" in r.text
    assert r.buttons == RESERVATION_MENU
    assert await bot.state(SELLER) == "BotState:main_menu"
    assert len(reservations()) == 1  # новая не создаётся


async def test_taken_seat_is_refused(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(ADMIN, "", fwd_from=BUYER2)
    [r] = await bot.send(ADMIN, "5")
    assert "Заняты: 3-5" in r.text
    [r] = await bot.send(ADMIN, "4")
    assert "недоступны" in r.text
    assert await bot.state(ADMIN) == "BotState:awaiting_seats"
    assert (5, 4, "booked") in seats() and len(seats()) == 3


async def test_cancel_command_resets_state(bot):
    await bot.send(SELLER, "", fwd_from=BUYER)
    [r] = await bot.send(SELLER, "/cancel")
    assert r.text.startswith("Операция отменена.")
    # Как сейчас: посреди брони состояние удаляется, из меню брони — idle
    assert await bot.state(SELLER) in (None, "BotState:idle")


async def test_context_switch_to_another_buyer(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(SELLER, "", fwd_from=BUYER2)
    await bot.send(SELLER, "6")
    [r] = await bot.send(SELLER, "", fwd_from=BUYER)  # посреди ввода мест — другой покупатель
    assert "Переключиться на Иван Покупатель?" in r.text
    assert r.buttons == ["Да", "Нет"]
    [r] = await bot.send(SELLER, "Да")
    assert r.text.startswith("Бронь #1 — Иван Покупатель")
    assert await bot.state(SELLER) == "BotState:main_menu"


# --- оплата ---------------------------------------------------------------


async def test_payment_by_receipt(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")

    [r] = await bot.send(SELLER, "", fwd_from=BUYER, fwd_attachments=[photo(BUYER)])
    assert "Сколько мест оплачено?" in r.text
    assert r.buttons == ["1", "2", "3", "Отмена"]
    assert await bot.state(SELLER) == "BotState:payment_quantity"

    replies = await bot.send(SELLER, "2")
    to_seller = [m for m in replies if m.peer_id == SELLER]
    to_admin = [m for m in replies if m.peer_id == ADMIN]
    assert "Оплачено 2 места" in to_seller[0].text
    assert "Сумма: 3000 руб." in to_seller[0].text
    assert "Осталось к оплате: 1 место" in to_seller[0].text
    # Админы получают уведомление об оплате
    assert len(to_admin) == 1 and "Оплата зафиксирована" in to_admin[0].text
    # …с чеком: он загружается один раз (в диалог билетёра), та же строка
    # вложения уходит админам и сохраняется в оплате
    assert [peer for peer, _ in bot.vk.reuploaded] == [SELLER]
    assert to_admin[0].attachment == f"photo{SELLER}_1"

    # Оплачиваются места по порядку (ряд, место): 3 и 4
    assert seats() == [(5, 3, "paid"), (5, 4, "paid"), (5, 5, "booked")]
    with SessionLocal() as session:
        [payment] = session.scalars(select(Payment))
        assert payment.seat_count == 2 and payment.payment_amount == 3000
        assert payment.vk_message_ts is not None  # время сообщения с чеком
        assert payment.receipt_attachments == f"photo{SELLER}_1"


async def test_payment_button_asks_for_receipt(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(SELLER, "", fwd_from=BUYER)
    [r] = await bot.send(SELLER, "Оплата")
    assert "перешлите чек" in r.text
    assert seats(SeatStatus.PAID) == []


# --- удаление и отмена ----------------------------------------------------


async def test_delete_seat(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(SELLER, "", fwd_from=BUYER)
    [r] = await bot.send(SELLER, "Удалить")
    assert "номер ряда для удаления" in r.text
    [r] = await bot.send(SELLER, "5")
    assert "места 3-5. Какие удалить?" in r.text
    [r] = await bot.send(SELLER, "5")
    assert r.buttons == ["Подтвердить", "Отмена"]
    replies = await bot.send(SELLER, "Подтвердить")
    assert replies[0].text == "Удалено 1 место."
    # Как сейчас: следом — обновлённый текст брони для клиента и меню брони
    assert "Места забронированы" in replies[1].text
    assert replies[2].buttons == RESERVATION_MENU
    assert seats() == [(5, 3, "booked"), (5, 4, "booked")]


async def test_seller_cannot_cancel_paid_reservation(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(SELLER, "", fwd_from=BUYER, fwd_attachments=[photo(BUYER)])
    await bot.send(SELLER, "1")
    await bot.send(SELLER, "", fwd_from=BUYER)
    [r] = await bot.send(SELLER, "Удалить все")
    assert "Отмена доступна только админам" in r.text
    assert reservations()[0].state == ReservationState.ACTIVE


async def test_admin_cancels_reservation(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(ADMIN, "", fwd_from=BUYER)
    [r] = await bot.send(ADMIN, "Удалить все")
    assert "Отменить бронь Иван Покупатель?" in r.text
    assert await bot.state(ADMIN) == "BotState:cancel_confirm"
    await bot.send(ADMIN, "Подтвердить")
    assert reservations()[0].state == ReservationState.CANCELLED
    assert seats() == []  # места освобождены


# --- резерв ---------------------------------------------------------------


async def test_reserve_add_and_remove(bot):
    [r] = await bot.send(ADMIN, "Резерв")
    assert "Активных резервов нет" in r.text
    await bot.send(ADMIN, "Добавить")
    await bot.send(ADMIN, "1")
    [r] = await bot.send(ADMIN, "1-2")
    assert "комментарий" in r.text
    [r] = await bot.send(ADMIN, "Для гостей")
    assert "Резерв создан" in r.text and "Для гостей" in r.text
    assert seats() == [(1, 1, "reserved"), (1, 2, "reserved")]

    await bot.send(ADMIN, "Удалить")
    [r] = await bot.send(ADMIN, "1")
    assert "зарезервированы: 1-2" in r.text
    await bot.send(ADMIN, "1")
    [r] = await bot.send(ADMIN, "Подтвердить")
    assert "Резерв снят" in r.text
    assert seats() == [(1, 2, "reserved")]


# --- должники -------------------------------------------------------------


async def test_debtors_empty(bot):
    [r] = await bot.send(SELLER, "Должники")
    assert r.text == "Должников нет."
    assert r.buttons == ["Обновить"]


# --- пользователи (только владелец) ---------------------------------------


async def test_add_seller_only_by_owner(bot):
    [r] = await bot.send(SELLER, "/addseller", fwd_from=NEWBIE)
    assert r.text == "Команда доступна только владельцу проекта."

    [r] = await bot.send(OWNER, "/addseller", fwd_from=NEWBIE)
    assert "Новый Билетёр (vk.com/id401) добавлен как билетер" in r.text
    with SessionLocal() as session:
        user = session.scalar(select(AppUser).where(AppUser.vk_user_id == NEWBIE))
        assert user.role == UserRole.SELLER and user.is_active

    [r] = await bot.send(OWNER, "/users")
    assert "Новый Билетёр (билетер)" in r.text
