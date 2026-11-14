"""
Веб: страницы и действия через httpx по ASGI (без сервера), база — временная.

Фиксируют поведение перед перестройкой веба (ROADMAP, этап 7, шаг 6).
HTML разбирается по устойчивым признакам: классы мест на схеме зала,
JSON со списком на «дне концерта», значения статистики на странице оплат.
"""

import json
import re

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from tickets.db import SessionLocal, unit_of_work
from tickets.models.base import UserRole
from tickets.models.payment import Payment
from tickets.services import payments, reservations, seats, users

pytestmark = pytest.mark.asyncio

PASSWORD = "test"  # PAYMENTS_PASSWORD из conftest.py


@pytest_asyncio.fixture
async def client():
    from tickets.web.main import app

    # https: cookie входа Secure (COOKIE_SECURE по умолчанию true)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin(client) -> httpx.AsyncClient:
    """Клиент, вошедший на страницу оплат."""
    r = await client.post("/payments/login", data={"password": PASSWORD})
    assert r.status_code == 303 and r.headers["location"] == "/payments"
    return client


@pytest_asyncio.fixture
async def data():
    """Две брони (одна частично оплачена) и резерв."""
    async with unit_of_work() as s:
        seller = await users.add_app_user(s, 201, "Билетёр", UserRole.SELLER)
        ivan = await users.get_or_create_vk_user(s, 301, "Иван Покупатель")
        petr = await users.get_or_create_vk_user(s, 302, "Пётр Второй")
        r1 = await reservations.create(s, ivan.id, seller.id)
        await reservations.add_seats(s, r1.id, 5, [3, 4, 5], seller.id)
        r2 = await reservations.create(s, petr.id, seller.id)
        await reservations.add_seats(s, r2.id, 7, [1], seller.id)
        await payments.record(s, r1.id, 2, seller.id)
        await seats.add_reserve(s, 1, [1, 2], "Для гостей", seller.id)
    return {"r1": r1.id, "r2": r2.id}


def stat(html: str, label: str) -> str:
    """Значение из блока статистики: <span>Бронь</span><span class="val">3</span>."""
    m = re.search(rf"<span>{label}</span><span class=\"val\">([^<]+)</span>", html)
    assert m, label
    return m.group(1).strip()


# --- публичное --------------------------------------------------------------


async def test_hall_shows_occupied_seats(client, data):
    r = await client.get("/")
    assert r.status_code == 200
    assert r.text.count('class="seat occupied"') == 6  # 3 + 1 места броней + 2 резерва


async def test_favicon(client):
    r = await client.get("/favicon.ico")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


# --- вход -------------------------------------------------------------------


async def test_protected_pages_redirect_to_login(client):
    for path in ("/payments", "/concert-day"):
        r = await client.get(path)
        assert r.status_code == 303 and r.headers["location"] == "/payments/login", path


async def test_wrong_password(client):
    r = await client.post("/payments/login", data={"password": "wrong"})
    assert r.status_code == 200 and "Неверный пароль" in r.text
    assert (await client.get("/payments")).status_code == 303


async def test_login_cookie_is_secure_and_httponly(client):
    r = await client.post("/payments/login", data={"password": PASSWORD})
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "samesite=lax" in cookie.lower()


# --- день концерта ----------------------------------------------------------


async def test_concert_day_lists_bookings_and_reserves(admin, data):
    r = await admin.get("/concert-day")
    assert r.status_code == 200
    entries = json.loads(re.search(r"const entries = (\[.*?\]);\n", r.text).group(1))
    by_name = {e["buyer_name"]: e for e in entries}
    # Имя показывается как «Фамилия Имя»; список по алфавиту
    assert list(by_name) == ["Второй Пётр", "Для гостей", "Покупатель Иван"]
    assert by_name["Покупатель Иван"]["status_key"] == "partial"
    assert by_name["Покупатель Иван"]["status_text"] == "частично (2 из 3)"
    assert by_name["Покупатель Иван"]["seat_lines"] == ["Ряд 5, места: 3-5"]
    assert by_name["Второй Пётр"]["status_key"] == "unpaid"
    assert by_name["Для гостей"]["status_key"] == "reserved"
    assert "Броней: <span>3</span>, мест: <span>6</span>" in r.text


# --- оплаты -----------------------------------------------------------------


async def test_payments_page_stats(admin, data):
    r = await admin.get("/payments")
    assert r.status_code == 200
    assert stat(r.text, "Бронь") == "2"  # 1 у Ивана + 1 у Петра
    assert stat(r.text, "Оплачено") == "2"
    assert stat(r.text, "Резерв") == "2"
    assert "Иван Покупатель" in r.text  # оплата в списке непроверенных


async def test_verify_all_marks_payments_verified(admin, data):
    r = await admin.post("/payments/verify-all")
    assert r.status_code == 303 and r.headers["location"] == "/payments"
    with SessionLocal() as session:
        assert [p.is_verified for p in session.scalars(select(Payment))] == [True]


async def test_verify_requires_login(client, data):
    r = await client.post("/payments/verify-all")
    assert r.status_code == 303 and r.headers["location"] == "/payments/login"
    with SessionLocal() as session:
        assert [p.is_verified for p in session.scalars(select(Payment))] == [False]


# --- ошибки -----------------------------------------------------------------


async def test_unhandled_error_is_500_and_notifies(client, monkeypatch):
    from tickets.web import main as web_main
    from tickets.web.routers import public

    sent = []

    async def fake_notify(text, **kwargs):
        sent.append(text)

    def broken_layout():
        raise RuntimeError("layout broken")

    monkeypatch.setattr(web_main, "notify_owner", fake_notify)
    monkeypatch.setattr(public, "get_layout", broken_layout)
    r = await client.get("/")
    assert r.status_code == 500 and r.text == "Internal Server Error"
    assert sent == ["⚠️ Ошибка 500 в вебе: GET /: RuntimeError: layout broken"]


async def test_verify_all_is_audited_with_ip(admin, data):
    from tickets.models.audit import AuditLog
    from tickets.models.base import ActorType

    with SessionLocal() as session:
        [payment_id] = session.scalars(select(Payment.id))
    await admin.post("/payments/verify-all", headers={"X-Real-IP": "203.0.113.7"})
    await admin.post("/payments/verify-all")  # нечего отмечать — второй записи нет

    with SessionLocal() as session:
        [entry] = session.scalars(
            select(AuditLog).where(AuditLog.action_type == "payments_verified")
        )
    assert entry.actor_type == ActorType.WEB_ADMIN and entry.actor_user_id is None
    assert entry.payload == {"payment_ids": [payment_id], "ip": "203.0.113.7"}


async def test_per_payment_verify_is_gone(admin, data):
    """По одной оплаты не отмечаются: только «Проверено» для всех."""
    assert (await admin.post("/payments/1/verify")).status_code == 404
    assert (await admin.post("/payments/checkpoint")).status_code == 404
    page = (await admin.get("/payments")).text
    assert 'type="checkbox"' not in page
    assert 'action="/payments/verify-all"' in page
    assert "chart.js@4.6.1" in page and 'integrity="sha384-' in page
