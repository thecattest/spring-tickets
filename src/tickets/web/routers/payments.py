"""Страница оплат (вход по паролю): статистика, новые и проверенные оплаты, «Проверено»."""

import logging
from decimal import Decimal

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from tickets.config import app_settings, web_settings
from tickets.hall import get_layout
from tickets.services import payments
from tickets.web import deps
from tickets.web.deps import Admin, Session
from tickets.web.filters import templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(deps.LOGIN_PATH)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "payments_login.html", {"error": error})


@router.post(deps.LOGIN_PATH)
async def login(request: Request, password: str = Form(...)):
    # Попытки входа ограничены в nginx (limit_req на этот путь), не аудируются
    if not deps.password_ok(password):
        return templates.TemplateResponse(
            request, "payments_login.html", {"error": "Неверный пароль"}
        )
    response = RedirectResponse("/payments", status_code=303)
    response.set_cookie(
        deps.COOKIE_NAME,
        deps.login_token(),
        max_age=deps.COOKIE_MAX_AGE,
        httponly=True,
        secure=web_settings().cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/payments")
async def payments_page(request: Request, session: Session, _: Admin):
    data = await payments.page(session)
    by_status = data["seats_by_status"]
    booked, paid, reserved = (by_status.get(k, 0) for k in ("booked", "paid", "reserved"))
    total_seats = sum(row["seatCount"] for row in get_layout()["rows"].values())
    seat_price = app_settings().seat_price

    rows = [
        {
            "id": r["payment"].id,
            "buyer_name": r["buyer_name"],
            "buyer_vk_id": r["buyer_vk_id"],
            "seller_name": r["seller_name"],
            "seat_count": r["payment"].seat_count,
            "amount": float(r["payment"].payment_amount),
            "date": r["payment"].recorded_at,
            "receipt_attachments": r["payment"].receipt_attachments,
            "is_verified": r["payment"].is_verified,
        }
        for r in data["payments"]
    ]
    return templates.TemplateResponse(
        request,
        "payments.html",
        {
            "unverified_payments": [r for r in rows if not r["is_verified"]],
            "verified_payments": [r for r in rows if r["is_verified"]],
            "seat_stats": {
                "free": total_seats - booked - paid - reserved,
                "booked": booked,
                "paid": paid,
                "reserved": reserved,
            },
            "money_stats": {
                "paid": float(data["total_paid"]),
                "projected": float(Decimal(booked * seat_price)),
            },
            "seat_price": seat_price,
        },
    )


@router.post("/payments/verify-all")
async def verify_all(request: Request, session: Session, _: Admin):
    """«Проверено» — все текущие непроверенные оплаты; одна запись аудита с id и IP."""
    await payments.verify_all(session, ip=deps.client_ip(request))
    return RedirectResponse("/payments", status_code=303)
