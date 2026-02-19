"""
Web app serving a public hall seat map and admin payments page.

Run:
    uvicorn web.app:app --host 0.0.0.0 --port 5000
"""

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import func

from bot.utils.layout import get_layout
from database import get_session
from models.base import SeatStatus
from models.payment import Payment
from models.reconcile import ReconcileCheckpoint
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

    with get_session() as session:
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

    with get_session() as session:
        # Fetch all payments with joins
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
            .order_by(Payment.recorded_at.desc())
            .all()
        )

        # Fetch checkpoints
        checkpoints = (
            session.query(ReconcileCheckpoint)
            .order_by(ReconcileCheckpoint.checked_at.desc())
            .all()
        )

        # Seat stats
        seat_counts = (
            session.query(SeatAssignment.status, func.count())
            .filter(SeatAssignment.released_at.is_(None))
            .group_by(SeatAssignment.status)
            .all()
        )

        # Money stats
        total_paid = (
            session.query(func.coalesce(func.sum(Payment.payment_amount), 0))
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

    # Group payments into sections by checkpoint boundaries
    checkpoint_times = [cp.checked_at for cp in checkpoints]

    # Build payment rows
    payment_rows = []
    for p, buyer_name, buyer_vk_id, seller_name in payments_query:
        payment_rows.append({
            "buyer_name": buyer_name,
            "buyer_vk_id": buyer_vk_id,
            "seller_name": seller_name,
            "seat_count": p.seat_count,
            "amount": float(p.payment_amount),
            "date": p.recorded_at,
        })

    # Section 0: payments after latest checkpoint (or all if no checkpoints)
    sections = []
    latest_cp_time = checkpoint_times[0] if checkpoint_times else None

    new_payments = []
    older_payments = []
    for row in payment_rows:
        if latest_cp_time is None or row["date"] > latest_cp_time:
            new_payments.append(row)
        else:
            older_payments.append(row)

    sections.append({
        "label": None,  # Current (no checkpoint header)
        "payments": new_payments,
    })

    # For each checkpoint, group payments between this checkpoint and the next older one
    for i, cp in enumerate(checkpoints):
        cp_time = cp.checked_at
        next_cp_time = checkpoint_times[i + 1] if i + 1 < len(checkpoint_times) else None

        section_payments = []
        for row in older_payments:
            if next_cp_time is not None:
                if next_cp_time < row["date"] <= cp_time:
                    section_payments.append(row)
            else:
                if row["date"] <= cp_time:
                    section_payments.append(row)

        sections.append({
            "label": f"Проверено {cp.checked_at.strftime('%d.%m.%Y %H:%M')}",
            "count": len(section_payments),
            "payments": section_payments,
        })

    has_new_payments = len(new_payments) > 0

    return templates.TemplateResponse("payments.html", {
        "request": request,
        "sections": sections,
        "seat_stats": seat_stats,
        "money_stats": money_stats,
        "seat_price": SEAT_PRICE,
        "has_new_payments": has_new_payments,
    })


# ---------------------------------------------------------------------------
# Checkpoint creation
# ---------------------------------------------------------------------------

@app.post("/payments/checkpoint")
def create_checkpoint(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/payments/login", status_code=303)

    with get_session() as session:
        # Check there are payments after the latest checkpoint
        latest_cp = (
            session.query(ReconcileCheckpoint.checked_at)
            .order_by(ReconcileCheckpoint.checked_at.desc())
            .first()
        )
        query = session.query(func.count()).select_from(Payment)
        if latest_cp:
            query = query.filter(Payment.recorded_at > latest_cp.checked_at)
        new_count = query.scalar()

        if not new_count:
            return RedirectResponse("/payments", status_code=303)

        checkpoint = ReconcileCheckpoint(
            checked_by_user_id=None,
            checked_at=datetime.utcnow(),
        )
        session.add(checkpoint)

    return RedirectResponse("/payments", status_code=303)
