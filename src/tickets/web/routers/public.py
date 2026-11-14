"""Публичное: схема зала с занятыми местами и favicon."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from tickets.hall import get_layout
from tickets.services import reports
from tickets.web.deps import Session
from tickets.web.filters import templates

router = APIRouter()

_FAVICON = Path(__file__).resolve().parent.parent / "favicon.png"


@router.get("/favicon.ico")
@router.get("/favicon.png")
async def favicon():
    return FileResponse(_FAVICON, media_type="image/png")


@router.get("/")
async def hall(request: Request, session: Session):
    occupied = await reports.occupied_seats(session)
    layout = get_layout()
    row_count = len(layout["rows"])

    rows = []
    for row in range(1, row_count + 1):
        seat_count = layout["rows"][str(row)]["seatCount"]
        rows.append(
            {
                "row_number": row,
                "seats": [
                    {"number": seat, "occupied": (row, seat) in occupied}
                    for seat in range(1, seat_count + 1)
                ],
            }
        )
    total = sum(len(r["seats"]) for r in rows)

    meta = layout["layout"]
    aisles = meta.get("verticalAisles", [])
    # Ряды с проходами: "10-24" → с 10-го; проходов нет — за пределами зала
    aisle_row_start = min((int(a["rows"].split("-")[0]) for a in aisles), default=row_count + 1)
    return templates.TemplateResponse(
        request,
        "hall.html",
        {
            "rows": rows,
            "layout_meta": {
                **meta,
                "max_seat_count": max(r["seatCount"] for r in layout["rows"].values()),
                "aisle_seats": [a["afterSeat"] for a in aisles],
                "aisle_row_start": aisle_row_start,
            },
            "total_seats": total,
            "total_occupied": len(occupied),
            "total_free": total - len(occupied),
        },
    )
