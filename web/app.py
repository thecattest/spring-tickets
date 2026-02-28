"""
Web app serving a public hall seat map and admin payments page.

Run:
    uvicorn web.app:app --host 0.0.0.0 --port 5000
"""

import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import func

from bot.utils.layout import get_layout
from database import SessionLocal
from models.base import SeatStatus
from models.payment import Payment, PaymentSeat
from models.reservation import Reservation
from models.seat_assignment import SeatAssignment
from models.user import AppUser
from models.vk_user import VkUser

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

PAYMENTS_PASSWORD = os.getenv("PAYMENTS_PASSWORD", "")
SEAT_PRICE = int(os.getenv("SEAT_PRICE", "1500"))
COOKIE_SECRET = os.getenv("COOKIE_SECRET", PAYMENTS_PASSWORD + "_secret")
COOKIE_MAX_AGE = 24 * 60 * 60  # 24 hours

serializer = URLSafeTimedSerializer(COOKIE_SECRET)
COOKIE_NAME = "payments_auth"


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        serializer.loads(token, max_age=COOKIE_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


# ---------------------------------------------------------------------------
# Hall map (public)
# ---------------------------------------------------------------------------

@app.get("/")
def hall(request: Request):
    layout = get_layout()

    with SessionLocal() as session:
        occupied_rows = (
            session.query(SeatAssignment.row_number, SeatAssignment.seat_number)
            .filter(SeatAssignment.released_at.is_(None))
            .all()
        )
    occupied_set = {(r, s) for r, s in occupied_rows}

    row_count = len(layout["rows"])
    rows_data = []
    total_seats = 0
    total_occupied = 0

    for row_num in range(1, row_count + 1):
        seat_count = layout["rows"][str(row_num)]["seatCount"]
        seats = []
        for seat_num in range(1, seat_count + 1):
            is_occupied = (row_num, seat_num) in occupied_set
            seats.append({"number": seat_num, "occupied": is_occupied})
            total_seats += 1
            if is_occupied:
                total_occupied += 1
        rows_data.append({"row_number": row_num, "seats": seats})

    # Derive template-friendly layout meta from config
    layout_meta = layout["layout"]
    max_seat_count = max(r["seatCount"] for r in layout["rows"].values())
    aisle_seats = [a["afterSeat"] for a in layout_meta.get("verticalAisles", [])]
    # Parse aisle row range (e.g. "10-24") to get start row
    aisle_row_start = row_count + 1  # default: no aisles
    for a in layout_meta.get("verticalAisles", []):
        start = int(a["rows"].split("-")[0])
        aisle_row_start = min(aisle_row_start, start)

    return templates.TemplateResponse("hall.html", {
        "request": request,
        "rows": rows_data,
        "layout_meta": {
            **layout_meta,
            "max_seat_count": max_seat_count,
            "aisle_seats": aisle_seats,
            "aisle_row_start": aisle_row_start,
        },
        "total_seats": total_seats,
        "total_occupied": total_occupied,
        "total_free": total_seats - total_occupied,
    })


# ---------------------------------------------------------------------------
# Payments auth
# ---------------------------------------------------------------------------

@app.get("/payments/login")
def payments_login(request: Request, error: str = ""):
    return templates.TemplateResponse("payments_login.html", {
        "request": request,
        "error": error,
    })


@app.post("/payments/login")
def payments_login_post(request: Request, password: str = Form(...)):
    if password == PAYMENTS_PASSWORD:
        token = serializer.dumps("authenticated")
        response = RedirectResponse("/payments", status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response
    return templates.TemplateResponse("payments_login.html", {
        "request": request,
        "error": "Неверный пароль",
    })


# ---------------------------------------------------------------------------
# Payments page
# ---------------------------------------------------------------------------

@app.get("/payments")
def payments_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/payments/login", status_code=303)

    with SessionLocal() as session:
        # Subquery: count active (non-released) seats per payment
        active_seat_count = (
            session.query(func.count(PaymentSeat.payment_id))
            .join(SeatAssignment, PaymentSeat.seat_assignment_id == SeatAssignment.id)
            .filter(
                PaymentSeat.payment_id == Payment.id,
                SeatAssignment.released_at.is_(None),
            )
            .correlate(Payment)
            .scalar_subquery()
        )

        # Fetch payments that have at least one active seat
        payments_query = (
            session.query(
                Payment,
                VkUser.display_name.label("buyer_name"),
                VkUser.vk_user_id.label("buyer_vk_id"),
                AppUser.display_name.label("seller_name"),
            )
            .join(Reservation, Payment.reservation_id == Reservation.id)
            .join(VkUser, Reservation.buyer_vk_user_id == VkUser.id)
            .join(AppUser, Payment.recorded_by_user_id == AppUser.id)
            .filter(active_seat_count > 0)
            .order_by(Payment.recorded_at.desc())
            .all()
        )

        # Seat stats
        seat_counts = (
            session.query(SeatAssignment.status, func.count())
            .filter(SeatAssignment.released_at.is_(None))
            .group_by(SeatAssignment.status)
            .all()
        )

        # Money stats — only payments with at least one active seat
        total_paid = (
            session.query(func.coalesce(func.sum(Payment.payment_amount), 0))
            .filter(active_seat_count > 0)
            .scalar()
        )

        # Count booked (unpaid) seats
        booked_count = (
            session.query(func.count())
            .select_from(SeatAssignment)
            .filter(
                SeatAssignment.released_at.is_(None),
                SeatAssignment.status == SeatStatus.BOOKED,
            )
            .scalar()
        )

    # Calculate total seats from layout
    layout = get_layout()
    total_seats = sum(row["seatCount"] for row in layout["rows"].values())

    # Process seat counts
    status_map = {s.value: c for s, c in seat_counts}
    booked = status_map.get("booked", 0)
    paid = status_map.get("paid", 0)
    reserved = status_map.get("reserved", 0)
    occupied = booked + paid + reserved
    free = total_seats - occupied

    seat_stats = {
        "free": free,
        "booked": booked,
        "paid": paid,
        "reserved": reserved,
    }

    # Money stats
    total_paid_decimal = Decimal(str(total_paid)) if total_paid else Decimal("0")
    projected = Decimal(str(booked_count * SEAT_PRICE))
    money_stats = {
        "paid": float(total_paid_decimal),
        "projected": float(projected),
    }

    # Build payment rows, split by is_verified
    unverified_payments = []
    verified_payments = []
    for p, buyer_name, buyer_vk_id, seller_name in payments_query:
        row = {
            "id": p.id,
            "buyer_name": buyer_name,
            "buyer_vk_id": buyer_vk_id,
            "seller_name": seller_name,
            "seat_count": p.seat_count,
            "amount": float(p.payment_amount),
            "date": p.recorded_at,
            "is_verified": p.is_verified,
        }
        if p.is_verified:
            verified_payments.append(row)
        else:
            unverified_payments.append(row)

    return templates.TemplateResponse("payments.html", {
        "request": request,
        "unverified_payments": unverified_payments,
        "verified_payments": verified_payments,
        "seat_stats": seat_stats,
        "money_stats": money_stats,
        "seat_price": SEAT_PRICE,
    })


# ---------------------------------------------------------------------------
# Payment verification
# ---------------------------------------------------------------------------

@app.post("/payments/{payment_id}/verify")
def toggle_verify(request: Request, payment_id: int):
    if not is_authenticated(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    with SessionLocal() as session:
        payment = session.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            return JSONResponse({"error": "not found"}, status_code=404)

        payment.is_verified = not payment.is_verified
        session.commit()
        return JSONResponse({"is_verified": payment.is_verified})


@app.post("/payments/checkpoint")
def bulk_verify(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/payments/login", status_code=303)

    with SessionLocal() as session:
        updated = (
            session.query(Payment)
            .filter(Payment.is_verified == False)
            .update({"is_verified": True})
        )
        session.commit()

    return RedirectResponse("/payments", status_code=303)
