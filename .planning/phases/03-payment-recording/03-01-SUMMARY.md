---
phase: "03"
plan: "01"
name: "Payment Foundation Components"
subsystem: "payment"
tags: ["payment", "sqlalchemy", "migration", "fsm", "keyboard", "sqlite"]

one-liner: "Nullable Payment model + DB migration + PAYMENT_QUANTITY state + payment_quantity_keyboard + record_payment with deterministic seat selection"

dependency-graph:
  requires: ["02-01", "02-02", "02-03", "02-04"]
  provides: ["payment model", "record_payment", "payment_quantity_keyboard", "format_payment_confirmation", "PAYMENT_QUANTITY state"]
  affects: ["03-02"]

tech-stack:
  added: []
  patterns: ["deterministic partial payment (row ASC, seat ASC)", "atomic payment recording with flush+commit pattern", "SQLite table rebuild migration pattern"]

file-tracking:
  created: []
  modified:
    - "models/payment.py"
    - "bot/fsm/states.py"
    - "bot/keyboards.py"
    - "bot/messages.py"
    - "bot/utils/db.py"
    - "tickets.db"

decisions:
  - id: "nullable-receipt-fields"
    choice: "vk_message_url and vk_message_ts are Optional in Payment model"
    rationale: "Button-flow payments have no VK receipt, so fields must be nullable"
    alternatives: ["separate table for button payments", "required dummy URL"]
  - id: "sqlite-table-rebuild-migration"
    choice: "Rebuilt payments table using SQLite rename pattern when data exists"
    rationale: "SQLite does not support ALTER COLUMN; table rebuild is the only safe migration path"
    alternatives: ["Drop and recreate (would lose data)"]
  - id: "deterministic-seat-selection"
    choice: "First N BOOKED seats selected by row ASC, seat ASC"
    rationale: "Deterministic and predictable for partial payments; avoids ambiguity"
    alternatives: ["random selection", "last N seats", "let user pick seats"]

metrics:
  tasks-completed: 2
  tasks-total: 2
  deviations: 1
  duration: "4m"
  completed: "2026-02-18"
---

# Phase 03 Plan 01: Payment Foundation Components Summary

**One-liner:** Nullable Payment model + DB migration + PAYMENT_QUANTITY state + payment_quantity_keyboard + record_payment with deterministic seat selection

## What Was Built

All infrastructure prerequisites for payment recording in Plan 02:

1. **Payment model** (`models/payment.py`) — Made `vk_message_url` and `vk_message_ts` nullable (`Optional[str]` / `Optional[datetime]`) to support button-flow payments that have no VK receipt.

2. **DB Migration** (`tickets.db`) — Migrated live SQLite database using the table-rebuild pattern (SQLite doesn't support ALTER COLUMN). The existing payments table had 7 columns (missing `payment_amount` and `seat_count` which were added in Phase 0 to the model but never migrated). The migration preserved all existing data and added all missing columns with proper defaults.

3. **FSM state** (`bot/fsm/states.py`) — Added `PAYMENT_QUANTITY = "payment_quantity"` state to `BotState`, replacing the commented-out placeholder.

4. **Payment quantity keyboard** (`bot/keyboards.py`) — Added `payment_quantity_keyboard(booked_count: int)` generating:
   - Numbered buttons [1]..[N] at up to 5 per row
   - "Все N" button (omitted for N=1 as redundant)
   - "Отмена" button on its own row

5. **record_payment function** (`bot/utils/db.py`) — Atomic payment recording:
   - Queries BOOKED seats ordered by row ASC, seat ASC
   - Raises `InsufficientSeatsError` if requested > available
   - Creates `Payment` + `PaymentSeat` records
   - Updates seat status to PAID
   - Updates `reservation.last_activity_at`
   - Creates audit log with `payment_recorded` action

6. **format_payment_confirmation** (`bot/messages.py`) — Human-readable payment result using `format_seat_ranges` grouped by row, showing paid seats and remaining unpaid seats.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix Payment model + Migrate DB + Add FSM state + Add keyboard | 7891721 | models/payment.py, bot/fsm/states.py, bot/keyboards.py, tickets.db |
| 2 | Add record_payment DB function + payment confirmation formatter | 811a338 | bot/utils/db.py, bot/messages.py |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Nullable receipt fields | Optional in Payment model | Button-flow payments have no VK receipt |
| SQLite migration strategy | Table rebuild pattern | SQLite doesn't support ALTER COLUMN |
| Seat selection order | Row ASC, seat ASC | Deterministic and predictable for partial payments |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing payments table missing payment_amount and seat_count columns**

- **Found during:** Task 1 DB migration
- **Issue:** The live `tickets.db` payments table had only 7 columns (id, reservation_id, recorded_by_user_id, vk_message_url, vk_message_ts, recorded_at, note) — it was missing `payment_amount` and `seat_count` which were added to the ORM model in Phase 0 but never migrated to the actual database. The plan assumed only the `NOT NULL` constraint needed fixing, but the migration also needed to add two columns.
- **Fix:** Extended the table rebuild migration to use explicit column mapping (INSERT INTO ... SELECT with named columns), providing DEFAULT 0 for the missing columns in existing test data. Preserved all 1 existing payment record and 2 payment_seat records.
- **Files modified:** tickets.db
- **Commit:** 7891721

## Verification Results

All checks passed:
- Payment model imports without error
- Model-level: `vk_message_url nullable: True`, `vk_message_ts nullable: True`
- DB-level: both columns confirmed nullable in SQLite schema
- `PAYMENT_QUANTITY` state accessible as `BotState.PAYMENT_QUANTITY`
- `payment_quantity_keyboard(5)` generates 3 rows: `[1][2][3][4][5]`, `[Все 5]`, `[Отмена]`
- `payment_quantity_keyboard(7)` generates: `[1][2][3][4][5]`, `[6][7][Все 7]`, `[Отмена]`
- `payment_quantity_keyboard(1)` generates: `[1]`, `[Отмена]`
- `record_payment` and `InsufficientSeatsError` import successfully
- `format_payment_confirmation` imports successfully
- All existing tests: same pass/fail count as before (11 pre-existing failures, 22 passing — unchanged)

## Next Phase Readiness

Ready for Plan 03-02 (payment handlers). All prerequisites are in place:
- `record_payment(reservation_id, seat_count, user_id, vk_message_url, vk_message_ts)` ready for handler wiring
- `InsufficientSeatsError` ready for handler error handling
- `PAYMENT_QUANTITY` state ready for FSM transitions
- `payment_quantity_keyboard` ready for keyboard display
- `format_payment_confirmation` ready for confirmation messages
