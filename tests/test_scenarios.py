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
from tickets.db import SessionLocal, unit_of_work
from tickets.models.base import ReservationState, SeatStatus, UserRole
from tickets.models.payment import Payment
from tickets.models.reservation import Reservation
from tickets.models.seat_assignment import SeatAssignment
from tickets.models.user import AppUser
from tickets.models.vk_user import VkUser
from tickets.services import users as users_service

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
    async with unit_of_work() as session:
        await users_service.add_app_user(session, SELLER, "Билетёр", UserRole.SELLER)
        await users_service.add_app_user(session, ADMIN, "Админ", UserRole.ADMIN)
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


# --- источник покупателя: ответ, ссылка ------------------------------------


async def test_reply_instead_of_forward_creates_reservation(bot):
    [r] = await bot.send(SELLER, "", reply_from=BUYER)
    assert "Создана новая бронь для Иван Покупатель" in r.text
    assert await bot.state(SELLER) == "BotState:awaiting_row"


async def test_vk_profile_link_creates_reservation(bot):
    bot.vk.screen_names["ivan"] = BUYER
    [r] = await bot.send(SELLER, "https://vk.com/ivan")
    assert "Создана новая бронь для Иван Покупатель" in r.text
    [reservation] = reservations()
    with SessionLocal() as session:
        vk_user = session.get(VkUser, reservation.buyer_vk_user_id)
        assert vk_user.vk_user_id == BUYER


async def test_unknown_vk_link(bot):
    [r] = await bot.send(SELLER, "vk.com/nobody")
    assert r.text == "Пользователь VK не найден."
    assert reservations() == []


# --- меню брони -----------------------------------------------------------


async def test_add_seats_from_menu_returns_to_menu(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(SELLER, "", fwd_from=BUYER)
    [r] = await bot.send(SELLER, "Добавить")
    assert await bot.state(SELLER) == "BotState:awaiting_row"
    await bot.send(SELLER, "7")
    await bot.send(SELLER, "1-2")
    replies = await bot.send(SELLER, "Готово")
    assert "Места забронированы" in replies[0].text  # обновлённый текст для клиента
    assert replies[-1].buttons == RESERVATION_MENU  # из меню брони — обратно в меню
    assert await bot.state(SELLER) == "BotState:main_menu"
    assert len(seats()) == 5


async def test_exit_resets_state(bot):
    await bot.send(SELLER, "", fwd_from=BUYER)
    [r] = await bot.send(SELLER, "/exit")
    assert r.text.startswith("Сессия завершена")
    assert await bot.state(SELLER) is None


# --- чеки и переключение клиента ------------------------------------------


async def test_receipt_when_idle_goes_straight_to_payment(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    [r] = await bot.send(SELLER, "", fwd_from=BUYER, fwd_attachments=[photo(BUYER)])
    assert "Сколько мест оплачено?" in r.text
    assert await bot.state(SELLER) == "BotState:payment_quantity"


async def test_cancel_button_on_payment_returns_to_menu(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(SELLER, "", fwd_from=BUYER, fwd_attachments=[photo(BUYER)])
    [r] = await bot.send(SELLER, "Отмена")
    assert r.buttons == RESERVATION_MENU
    assert await bot.state(SELLER) == "BotState:main_menu"
    assert seats(SeatStatus.PAID) == []


async def test_receipt_from_other_buyer_in_menu_asks_to_switch(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(SELLER, "", fwd_from=BUYER)
    [r] = await bot.send(SELLER, "", fwd_from=BUYER2, fwd_attachments=[photo(BUYER2)])
    assert "Получен чек от Пётр Второй" in r.text and r.buttons == ["Да", "Нет"]

    # «Нет» — остаёмся с прежним клиентом в том же состоянии
    [r] = await bot.send(SELLER, "Нет")
    assert r.text == "Продолжаем работу с Иван Покупатель."
    assert await bot.state(SELLER) == "BotState:main_menu"


async def test_switch_to_buyer_without_reservation_creates_one(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(SELLER, "", fwd_from=BUYER)
    await bot.send(SELLER, "", fwd_from=BUYER2, fwd_attachments=[photo(BUYER2)])
    [r] = await bot.send(SELLER, "Да")
    assert "У Пётр Второй нет активной брони" in r.text
    assert await bot.state(SELLER) == "BotState:awaiting_row"
    assert len(reservations()) == 2


async def test_cancel_button_on_delete_confirm_steps_back(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(SELLER, "", fwd_from=BUYER)
    for text in ("Удалить", "5", "5"):
        await bot.send(SELLER, text)
    [r] = await bot.send(SELLER, "Отмена")
    # Как сейчас: «Отмена» — это команда /cancel (шаг назад), а не «отказ»
    assert r.text == "Введите номер ряда для удаления:"
    assert await bot.state(SELLER) == "BotState:deleting_row"
    assert len(seats()) == 3


# --- резерв ---------------------------------------------------------------


async def test_reserve_refuses_taken_seat(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(ADMIN, "Резерв")
    await bot.send(ADMIN, "Добавить")
    [r] = await bot.send(ADMIN, "5")
    assert "Заняты: 3-5" in r.text
    [r] = await bot.send(ADMIN, "4")
    assert "недоступны" in r.text
    assert await bot.state(ADMIN) == "BotState:reserve_adding_seats"


async def test_reserve_is_admin_only(bot):
    [r] = await bot.send(SELLER, "Резерв")
    assert r.text == "Управление резервами доступно только администраторам."


# --- должники и пользователи ----------------------------------------------


async def test_debtors_listed_for_admin(bot):
    await book(bot, SELLER, BUYER, "5", "3-5")
    [r] = await bot.send(ADMIN, "Должники")
    assert r.text.startswith("Должники (1)")
    assert "Иван Покупатель (vk.com/id301)" in r.text and "Долг: 4500 руб." in r.text


async def test_add_admin_and_remove_user(bot):
    [r] = await bot.send(OWNER, "/addadmin", fwd_from=NEWBIE)
    assert "добавлен как администратор" in r.text
    [r] = await bot.send(OWNER, "/removeuser", fwd_from=NEWBIE)
    assert "удалён из системы" in r.text
    with SessionLocal() as session:
        user = session.scalar(select(AppUser).where(AppUser.vk_user_id == NEWBIE))
        assert user.is_active is False
    [r] = await bot.send(OWNER, "/removeuser", fwd_from=OWNER)
    assert r.text == "Нельзя удалить самого себя."


# --- актуальность брони (этап 6) ------------------------------------------


async def test_reservation_cancelled_elsewhere_resets_seller(bot):
    """Билетёр в меню брони, админ в это время отменил её — следующий шаг билетёра."""
    await book(bot, SELLER, BUYER, "5", "3-5")
    await bot.send(SELLER, "", fwd_from=BUYER)  # билетёр в меню брони
    await bot.send(ADMIN, "", fwd_from=BUYER)
    await bot.send(ADMIN, "Удалить все")
    await bot.send(ADMIN, "Подтвердить")
    assert reservations()[0].state == ReservationState.CANCELLED

    [r] = await bot.send(SELLER, "Добавить")
    assert r.text == "Бронь #1 уже отменена. Перешлите сообщение клиента, чтобы начать заново."
    assert await bot.state(SELLER) is None
