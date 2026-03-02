# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Concert ticket management system for VK (VKontakte). Ticketers create seat reservations, record payments, and manage bookings via a VK bot. A web UI shows a public hall map and admin payments dashboard.

**Stack**: Python 3.14+, SQLAlchemy 2.0+, vkbottle (VK bot), FastAPI (web), Redis (bot FSM state), SQLite (MVP).

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in VK_BOT_TOKEN, VK_GROUP_ID, REDIS_PASSWORD, PAYMENTS_PASSWORD
python database.py    # create tables

# Run bot (requires Redis + VK token)
python -m bot

# Run web UI
./web/run.sh
# or: uvicorn web.app:app --host 0.0.0.0 --port 8080

# Run tests
pytest
python test_db.py  # manual integration test

# Debtors reminders (cron)
python scripts/send_debtors_reminders.py
```

## Architecture

Two interfaces share the same database and models:

- **Bot** (`bot/`) — VK bot using vkbottle with FSM (finite state machine) handlers. Redis stores FSM state. Handlers in `bot/handlers/` orchestrate conversations; business logic lives in `bot/utils/db.py`.
- **Web** (`web/app.py`) — FastAPI app with Jinja2 templates. Public hall map at `/`, password-protected payments dashboard at `/payments`.
- **Models** (`models/`) — SQLAlchemy ORM. `SeatAssignment` is the critical table: a partial unique index on `(row_number, seat_number) WHERE released_at IS NULL` prevents double-booking at the DB level.
- **Database** (`database.py`) — Engine, `SessionLocal` factory, `init_db()`. SQLite with foreign keys enabled via PRAGMA.

### Key data flow

```
VK message → bot handler → bot/utils/db.py → SQLAlchemy models → SQLite
                                                    ↓
Web UI (read-only) ← FastAPI ← SQLAlchemy queries ←─┘
```

All state changes are recorded in the `AuditLog` table.

## Key Domain Concepts

- **SeatAssignment**: source of truth for seat occupancy. Statuses: `booked`, `paid`, `reserved`. Soft-deleted via `released_at` timestamp.
- **Reservation**: groups seats for one buyer. One active reservation per VK user. Tracks `last_activity_at` for 7-day debtor detection.
- **Payment/PaymentSeat**: supports partial payments (pay for N of M seats). Deterministic seat selection (row ASC, seat ASC).
- **ReconcileCheckpoint**: marks a point-in-time for financial reconciliation on the payments page.
- **layout.json**: defines hall geometry (24 rows, variable seats, aisles). Used by both bot (validation) and web (rendering).

## Code Conventions

- Enums in `models/base.py`: `UserRole`, `ReservationState`, `SeatStatus`, `ActorType`
- Datetime fields use `*_at` suffix (`created_at`, `released_at`, `last_activity_at`)
- FK fields use `{entity}_{entity_id}` pattern (`buyer_vk_user_id`, `sold_by_user_id`)
- Session pattern: `with SessionLocal() as session:` — commit explicitly, auto-rollback on exception
- Seat input format: `"1-3,5,8-10"` — parsed by `bot/utils/seat_parser.py`
- Comments and user-facing messages are in Russian

## Configuration

Environment variables loaded from `.env` (see `.env.example`). Key vars: `VK_BOT_TOKEN`, `VK_GROUP_ID`, `REDIS_*`, `DATABASE_URL`, `SEAT_PRICE`, `PAYMENTS_PASSWORD`, `SQL_ECHO`.

Config centralized in `bot/config.py` for the bot; `database.py` reads `DATABASE_URL` and `SQL_ECHO` directly from env.
