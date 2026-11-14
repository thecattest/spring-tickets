"""
Web app serving a public hall seat map and admin payments page.

Run:
    uvicorn web.app:app --host 0.0.0.0 --port 5000
"""

import json
import logging
import secrets
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, text

from bot.utils.layout import get_layout
from config import app_settings, web_settings
from database import SessionLocal, engine
from logging_config import setup_logging
from models.base import SeatStatus
from models.payment import Payment, PaymentSeat
from models.reservation import Reservation
from models.seat_assignment import SeatAssignment
from models.user import AppUser
from models.vk_user import VkUser

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Время в БД — timestamptz (UTC); показываем в часовом поясе концерта
DISPLAY_TZ = app_settings().display_tz


def local_dt(value: datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Jinja-фильтр: UTC из БД → DISPLAY_TZ."""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(DISPLAY_TZ).strftime(fmt)


templates.env.filters["local_dt"] = local_dt

# Секреты обязательны и не пустые — без них WebSettings не создастся и веб не стартует
_web = web_settings()
PAYMENTS_PASSWORD = _web.payments_password.get_secret_value()
COOKIE_SECRET = _web.cookie_secret.get_secret_value()
COOKIE_SECURE = _web.cookie_secure
COOKIE_MAX_AGE = 24 * 60 * 60  # 24 hours
SEAT_PRICE = app_settings().seat_price

serializer = URLSafeTimedSerializer(COOKIE_SECRET)
COOKIE_NAME = "payments_auth"


_FAVICON_PATH = Path(__file__).parent / "favicon.png"


@app.get("/favicon.ico")
@app.get("/favicon.png")
def favicon():
    return FileResponse(_FAVICON_PATH, media_type="image/png")


@app.get("/health")
def health():
    """
    Для healthcheck Docker (позже — и для мониторинга): приложение отвечает
    и база доступна. Детали ошибки — только в лог, наружу не отдаём.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check failed: database unavailable")
        return JSONResponse({"status": "error"}, status_code=503)
    return {"status": "ok"}


class _SkipHealthAccessLog(logging.Filter):
    """Не писать в access-лог uvicorn успешные /health — healthcheck дёргает его каждые 10 с."""

    def filter(self, record: logging.LogRecord) -> bool:
        # args uvicorn.access: (client, method, path, http_version, status)
        args = record.args
        return not (
            isinstance(args, tuple) and len(args) == 5 and args[2] == "/health" and args[4] == 200
        )


logging.getLogger("uvicorn.access").addFilter(_SkipHealthAccessLog())


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

    return templates.TemplateResponse(
        request,
        "hall.html",
        {
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
        },
    )


# ---------------------------------------------------------------------------
# Concert day page (protected)
# ---------------------------------------------------------------------------


def _format_seat_ranges(seats: list[int]) -> str:
    """Format sorted seat numbers as compact ranges: [1,2,3,5] -> '1-3, 5'."""
    if not seats:
        return ""
    ranges: list[str] = []
    start = prev = seats[0]
    for s in seats[1:]:
        if s == prev + 1:
            prev = s
        else:
            ranges.append(str(start) if start == prev else f"{start}-{prev}")
            start = prev = s
    ranges.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(ranges)


@app.get("/concert-day")
def concert_day(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/payments/login", status_code=303)

    with SessionLocal() as session:
        # Bookings (booked/paid) — have reservation + buyer
        booking_rows = (
            session.query(
                SeatAssignment.row_number,
                SeatAssignment.seat_number,
                SeatAssignment.status,
                Reservation.id.label("reservation_id"),
                VkUser.display_name.label("buyer_name"),
                VkUser.profile_url.label("buyer_profile_url"),
            )
            .join(Reservation, SeatAssignment.reservation_id == Reservation.id)
            .join(VkUser, Reservation.buyer_vk_user_id == VkUser.id)
            .filter(
                SeatAssignment.released_at.is_(None),
                SeatAssignment.status.in_([SeatStatus.BOOKED, SeatStatus.PAID]),
            )
            .all()
        )

        # Reserves — no reservation, have note
        reserve_rows = (
            session.query(
                SeatAssignment.row_number,
                SeatAssignment.seat_number,
                SeatAssignment.note,
            )
            .filter(
                SeatAssignment.released_at.is_(None),
                SeatAssignment.status == SeatStatus.RESERVED,
            )
            .all()
        )

    # Group bookings by reservation
    reservations: dict[int, dict] = {}
    seats_by_res: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    statuses_by_res: dict[int, list[str]] = defaultdict(list)

    for row in booking_rows:
        rid = row.reservation_id
        if rid not in reservations:
            reservations[rid] = {
                "buyer_name": row.buyer_name,
                "buyer_profile_url": row.buyer_profile_url,
            }
        seats_by_res[rid][row.row_number].append(row.seat_number)
        statuses_by_res[rid].append(row.status.value)

    # Group reserves by note (each unique note = one entry)
    reserves_by_note: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    for row in reserve_rows:
        note = row.note or "Резерв"
        reserves_by_note[note][row.row_number].append(row.seat_number)

    # Find max row number across all data for seat line formatting
    all_row_nums: set[int] = set()
    for rid in seats_by_res:
        all_row_nums.update(seats_by_res[rid].keys())
    for note_seats in reserves_by_note.values():
        all_row_nums.update(note_seats.keys())
    max_row_digits = len(str(max(all_row_nums))) if all_row_nums else 1

    def _build_seat_lines(
        seats_by_row: dict[int, list[int]],
    ) -> tuple[list[str], str, int, int, int]:
        """Build formatted seat lines, search string, total, first_row, first_seat."""
        seat_lines = []
        total = 0
        first_row = first_seat = None
        for row_num in sorted(seats_by_row):
            seat_nums = sorted(seats_by_row[row_num])
            total += len(seat_nums)
            if first_row is None:
                first_row = row_num
                first_seat = seat_nums[0]
            # Pad row number for alignment: "Ряд  8, места: " vs "Ряд 12, места: "
            padded_row = str(row_num).rjust(max_row_digits)
            seat_lines.append(f"Ряд {padded_row}, места: {_format_seat_ranges(seat_nums)}")
        search = " ".join(seat_lines)
        return seat_lines, search, total, first_row or 0, first_seat or 0

    # Build entries from bookings
    entries = []
    for rid, info in reservations.items():
        seat_lines, seats_search, total_seats, first_row, first_seat = _build_seat_lines(
            seats_by_res[rid]
        )

        # Payment status
        statuses = statuses_by_res[rid]
        paid_count = statuses.count("paid")
        if paid_count == len(statuses):
            status_text = "оплачено"
            status_key = "paid"
        elif paid_count == 0:
            status_text = "не оплачено"
            status_key = "unpaid"
        else:
            status_text = f"частично ({paid_count} из {len(statuses)})"
            status_key = "partial"

        # VK stores "Имя Фамилия" — flip to "Фамилия Имя" for display
        name_parts = info["buyer_name"].split(None, 1)
        if len(name_parts) == 2:
            display_name = f"{name_parts[1]} {name_parts[0]}"
        else:
            display_name = info["buyer_name"]

        entries.append(
            {
                "buyer_name": display_name,
                "buyer_profile_url": info["buyer_profile_url"],
                "seat_lines": seat_lines,
                "seats_search": seats_search,
                "seat_count": total_seats,
                "status_text": status_text,
                "status_key": status_key,
                "first_row": first_row,
                "first_seat": first_seat,
            }
        )

    # Build entries from reserves
    for note, seats_by_row in reserves_by_note.items():
        seat_lines, seats_search, total_seats, first_row, first_seat = _build_seat_lines(
            seats_by_row
        )
        entries.append(
            {
                "buyer_name": note,
                "buyer_profile_url": None,
                "seat_lines": seat_lines,
                "seats_search": seats_search,
                "seat_count": total_seats,
                "status_text": "резерв",
                "status_key": "reserved",
                "first_row": first_row,
                "first_seat": first_seat,
            }
        )

    # Default sort: alphabetical by display name
    entries.sort(key=lambda e: e["buyer_name"].lower())

    return templates.TemplateResponse(
        request,
        "concert_day.html",
        {
            "entries": entries,
            "entries_json": json.dumps(entries, ensure_ascii=False),
            "total_entries": len(entries),
            "total_seats": sum(e["seat_count"] for e in entries),
        },
    )


# ---------------------------------------------------------------------------
# Payments auth
# ---------------------------------------------------------------------------


@app.get("/payments/login")
def payments_login(request: Request, error: str = ""):
    return templates.TemplateResponse(
        request,
        "payments_login.html",
        {
            "error": error,
        },
    )


@app.post("/payments/login")
def payments_login_post(request: Request, password: str = Form(...)):
    # Сравнение за постоянное время; bytes — compare_digest не принимает не-ASCII str
    if secrets.compare_digest(password.encode(), PAYMENTS_PASSWORD.encode()):
        token = serializer.dumps("authenticated")
        response = RedirectResponse("/payments", status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
        )
        return response
    return templates.TemplateResponse(
        request,
        "payments_login.html",
        {
            "error": "Неверный пароль",
        },
    )


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
            "receipt_attachments": p.receipt_attachments,
        }
        if p.is_verified:
            verified_payments.append(row)
        else:
            unverified_payments.append(row)

    return templates.TemplateResponse(
        request,
        "payments.html",
        {
            "unverified_payments": unverified_payments,
            "verified_payments": verified_payments,
            "seat_stats": seat_stats,
            "money_stats": money_stats,
            "seat_price": SEAT_PRICE,
        },
    )


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
        (
            session.query(Payment)
            .filter(Payment.is_verified.is_(False))
            .update({"is_verified": True})
        )
        session.commit()

    return RedirectResponse("/payments", status_code=303)
