"""«День концерта» (после входа): кто где сидит — брони и резервы, поиск по фамилии."""

import json
from collections import defaultdict

from fastapi import APIRouter, Request

from tickets.formatting import format_seat_ranges
from tickets.models.base import SeatStatus
from tickets.services import reports
from tickets.web.deps import Admin, Session
from tickets.web.filters import templates

router = APIRouter()


def _surname_first(name: str) -> str:
    """VK отдаёт «Имя Фамилия» — в списке по фамилии: «Фамилия Имя»."""
    parts = name.split(None, 1)
    return f"{parts[1]} {parts[0]}" if len(parts) == 2 else name


def _entry(
    name: str,
    url: str | None,
    seats_by_row: dict,
    status_text: str,
    status_key: str,
    row_width: int,
) -> dict:
    lines = [
        f"Ряд {str(row).rjust(row_width)}, места: {format_seat_ranges(sorted(seats_by_row[row]))}"
        for row in sorted(seats_by_row)
    ]
    first_row = min(seats_by_row) if seats_by_row else 0
    return {
        "buyer_name": name,
        "buyer_profile_url": url,
        "seat_lines": lines,
        "seats_search": " ".join(lines),
        "seat_count": sum(len(s) for s in seats_by_row.values()),
        "status_text": status_text,
        "status_key": status_key,
        "first_row": first_row,
        "first_seat": min(seats_by_row[first_row]) if seats_by_row else 0,
    }


def _payment_status(statuses: list[SeatStatus]) -> tuple[str, str]:
    paid = statuses.count(SeatStatus.PAID)
    if paid == len(statuses):
        return "оплачено", "paid"
    if paid == 0:
        return "не оплачено", "unpaid"
    return f"частично ({paid} из {len(statuses)})", "partial"


@router.get("/concert-day")
async def concert_day(request: Request, session: Session, _: Admin):
    bookings, reserves = await reports.concert_day(session)

    buyers: dict[int, dict] = {}
    booked_seats: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    statuses: dict[int, list[SeatStatus]] = defaultdict(list)
    for b in bookings:
        buyers.setdefault(b["reservation_id"], b)
        booked_seats[b["reservation_id"]][b["row"]].append(b["seat"])
        statuses[b["reservation_id"]].append(b["status"])

    reserved_seats: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    for r in reserves:
        reserved_seats[r["note"] or "Резерв"][r["row"]].append(r["seat"])

    # Ширина номера ряда — для ровных столбцов: «Ряд  8» / «Ряд 12»
    rows = {b["row"] for b in bookings} | {r["row"] for r in reserves}
    width = len(str(max(rows))) if rows else 1

    entries = [
        _entry(
            _surname_first(b["buyer_name"]),
            b["buyer_profile_url"],
            booked_seats[rid],
            *_payment_status(statuses[rid]),
            width,
        )
        for rid, b in buyers.items()
    ]
    entries += [
        _entry(note, None, by_row, "резерв", "reserved", width)
        for note, by_row in reserved_seats.items()
    ]
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
