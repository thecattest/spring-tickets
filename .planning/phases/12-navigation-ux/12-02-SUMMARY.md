---
phase: 12-navigation-ux
plan: 02
subsystem: bot
tags: [fsm, validation, row-validation, db, handlers, vkbottle]

# Dependency graph
requires:
  - phase: 09-fsm-config
    provides: FSM_CONFIG with all BotState definitions
  - phase: 11-handler-migration
    provides: texts.py with ERR_ROW_NO_* constants, db imported in all handlers
  - plan: 12-01
    provides: ERR_ROW_NO_AVAILABLE_SEATS / ERR_ROW_NO_BOOKED_SEATS / ERR_ROW_NO_RESERVED_SEATS in texts.py
provides:
  - get_available_seats_in_row() in db.py (free seats in row, for booking/reserve-add)
  - get_reservation_booked_seats_in_row() in db.py (reservation seats in row, for deletion)
  - get_reserved_seats_in_row() in db.py (RESERVED-status seats in row, for reserve-remove)
  - Early row validation in all 4 row-input handlers (NAV-03)
affects: [12-03-seat-addition-back]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Early row validation: query DB after layout validation, before FSM state transition
    - Context loaded early in deleting_row_handler (before validation, not after)
    - Row availability helpers return list[int] of seat numbers (not ORM objects)

key-files:
  created: []
  modified:
    - bot/utils/db.py
    - bot/handlers/reservation.py
    - bot/handlers/deletion.py
    - bot/handlers/reserve.py

key-decisions:
  - "Row availability helpers return list[int] — handlers only need emptiness check, not ORM objects"
  - "deleting_row_handler loads context before early validation — reservation_id needed for get_reservation_booked_seats_in_row"
  - "get_available_seats_in_row uses lazy import of get_seat_count inside function body — avoids circular import risk"
  - "All 4 handlers: early validation inserted AFTER handle_row_input success, BEFORE context update and state transition"

patterns-established:
  - "Early row validation pattern: call db helper, if empty send ERR_ROW_NO_* and return without state transition"
  - "deleting_row_handler early context load for reservation_id: moved before early validation, same context object used for state update"

# Metrics
duration: 2min
completed: 2026-02-19
---

# Phase 12 Plan 02: Early Row Validation Summary

**Early row validation in all 4 row-input handlers: 3 new db.py helpers query seat availability per row, preventing billeters from advancing to seat-input when no actionable seats exist**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-02-19T20:53:34Z
- **Completed:** 2026-02-19T20:55:15Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `get_available_seats_in_row(row)` to db.py: returns free seat numbers in row (all seats minus occupied)
- Added `get_reservation_booked_seats_in_row(reservation_id, row)` to db.py: returns seat numbers belonging to this reservation in row
- Added `get_reserved_seats_in_row(row)` to db.py: returns RESERVED-status seats with no reservation_id in row
- Wired early validation into `awaiting_row_handler` (reservation.py): checks available seats before AWAITING_SEATS transition
- Wired early validation into `deleting_row_handler` (deletion.py): loads context early for reservation_id, checks booked seats before DELETING_SEATS transition
- Wired early validation into `reserve_adding_row_handler` (reserve.py): checks available seats before RESERVE_ADDING_SEATS transition
- Wired early validation into `reserve_removing_row_handler` (reserve.py): checks reserved seats before RESERVE_REMOVING_SEATS transition
- All error messages use `.format(row=row)` consistently and reference constants from texts.py (added in Plan 12-01)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add row-level seat availability queries to db.py** - `4ff3638` (feat)
2. **Task 2: Wire early row validation into 4 row-input handlers** - `2b76ed5` (feat)

## Files Created/Modified

- `bot/utils/db.py` - Added 3 new functions at end of file: get_available_seats_in_row, get_reservation_booked_seats_in_row, get_reserved_seats_in_row
- `bot/handlers/reservation.py` - awaiting_row_handler: inserted early available-seats check
- `bot/handlers/deletion.py` - deleting_row_handler: moved context load before validation, inserted early booked-seats check with reservation_id guard
- `bot/handlers/reserve.py` - reserve_adding_row_handler: inserted early available-seats check; reserve_removing_row_handler: inserted early reserved-seats check

## Decisions Made

- Row availability helpers return `list[int]` (seat numbers) rather than ORM objects — handlers only need to check emptiness (`if not available:`), no further processing needed
- `get_available_seats_in_row` uses a lazy import of `get_seat_count` inside the function body — consistent with [09-steps] circular import avoidance pattern
- `deleting_row_handler`: context loaded early (before early validation) because `reservation_id` is needed for `get_reservation_booked_seats_in_row`. The same context object is then updated with `current_row` and passed to `storage.set()` — no duplicate context load
- All 3 db helpers use `SeatAssignment`, `SeatStatus`, `select`, `SessionLocal` — all already imported at module top of db.py, no new imports needed
- No new module-level imports added to handler files — `db` and `texts` were already imported in all 4 handler files

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — all text constants (ERR_ROW_NO_AVAILABLE_SEATS, ERR_ROW_NO_BOOKED_SEATS, ERR_ROW_NO_RESERVED_SEATS) were in place from Plan 12-01. All db.py imports (SeatAssignment, SeatStatus, select, SessionLocal) already present. Handler imports (db, texts) already present.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plans 12-01 and 12-02 complete and committed
- All 4 row-input handlers now have early row validation (NAV-03 fully implemented)
- Plan 12-03 (seat-addition back navigation) is the final plan in Phase 12
- No blockers for 12-03

---
*Phase: 12-navigation-ux*
*Completed: 2026-02-19*
