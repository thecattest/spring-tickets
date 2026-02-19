"""
Web app serving a public hall seat map.

Run:
    uvicorn web.app:app --host 0.0.0.0 --port 5000
"""

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from database import get_session
from models.seat_assignment import SeatAssignment

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

LAYOUT_PATH = Path(__file__).parent.parent / "layout.json"


def load_layout() -> dict:
    with open(LAYOUT_PATH) as f:
        return json.load(f)


@app.get("/")
def hall(request: Request):
    layout = load_layout()

    with get_session() as session:
        occupied_rows = (
            session.query(SeatAssignment.row_number, SeatAssignment.seat_number)
            .filter(SeatAssignment.released_at.is_(None))
            .all()
        )
    occupied_set = {(r, s) for r, s in occupied_rows}

    rows_data = []
    total_seats = 0
    total_occupied = 0

    for row_num in range(1, 25):
        seat_count = layout["rows"][str(row_num)]["seatCount"]
        seats = []
        for seat_num in range(1, seat_count + 1):
            is_occupied = (row_num, seat_num) in occupied_set
            seats.append({"number": seat_num, "occupied": is_occupied})
            total_seats += 1
            if is_occupied:
                total_occupied += 1
        rows_data.append({"row_number": row_num, "seats": seats})

    return templates.TemplateResponse("hall.html", {
        "request": request,
        "rows": rows_data,
        "layout_meta": layout["layout"],
        "total_seats": total_seats,
        "total_occupied": total_occupied,
        "total_free": total_seats - total_occupied,
    })
